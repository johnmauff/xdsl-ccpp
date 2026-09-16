"""fortran_preprocess — C-preprocessor directive support for Fortran source
text, feeding fparser2_to_meta's extraction pipeline.

fparser (fparser2_to_meta.py's own backend) does zero CPP evaluation of its
own -- it only tokenizes ``#if``/``#ifdef``/etc. as opaque directive nodes
(``fparser.two.C99Preprocessor``), it never resolves them. Real conditional
compilation must be run through an actual preprocessing pass *before*
fparser2_to_meta.py hands source text to ``FortranStringReader``.

Mirrors capgen-v1's own Fortran-source CPP engine
(``ccpp_framework/scripts/parse_tools/preprocess.py``: ``PreprocStack``,
``process_if_line``, ``process_line``, ``in_true_region``) in design --
written fresh for this codebase, not a line-for-line port:

- Same 8 directives: ``#ifdef``/``#ifndef``/``#if``/``#elif``/``#else``/
  ``#endif``/``#define``/``#undef``.
- Blank-not-delete: an excluded line becomes ``""``, never removed, so line
  numbers stay stable for fparser2's own line-number-based error messages.
- ``#if``/``#elif`` expressions are evaluated by textually mapping C-style
  operators to Python ones, then ``ast.parse(..., mode="eval")`` plus a
  restricted AST walk (``BoolOp``/``UnaryOp(Not)``/``Compare``/``Call``/
  ``Name``/``Constant`` only) -- never ``eval()``/``exec()``.

Two deliberate departures from capgen-v1's own semantics (a fresh
implementation is not required to reproduce its quirks):

1. An identifier used as a bare value in ``#if``/``#elif`` that is NOT in
   ``defines`` evaluates to ``0`` (the real C-preprocessor rule).
   capgen-v1's own ``preproc_item_value`` returns the identifier string
   instead, which produces surprising truthy results for a plain
   ``#if UNDEFINED_SYM``.
2. Numeric comparisons coerce both sides to ``int`` when possible, so a
   string-valued define (``"4"``) compares correctly against an integer
   literal (``4``) -- capgen-v1's own ``Eq``/``NotEq`` handling does a raw
   Python ``==`` with no such coercion.

Out of scope (matches the actual CAM_CONFIG_OPTS use case, which only ever
needs simple object-like defines): function-like macros (``#define F(x)``),
macro body substitution into surrounding text, and ``#include``. A ``#``
line that isn't one of the 8 recognized directives is left untouched --
fparser's own ``C99Preprocessor`` node types already tolerate directives
this module doesn't understand (e.g. ``#include``).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

_DIRECTIVE_RE = re.compile(
    r"^\s*#\s*(ifdef|ifndef|if|elif|else|endif|define|undef)\b\s*(.*)$"
)


def parse_preproc_defines(raw_defines: list[str] | None) -> dict[str, str | None]:
    """Normalize a list of raw '-D'-style tokens into a symbol->value dict.

    Each entry may be ``NAME``, ``-DNAME``, ``NAME=VALUE``, or
    ``-DNAME=VALUE``. A bare define (no ``=``) maps to ``None``.

    >>> parse_preproc_defines(['-DSPMD', 'NP=4', '-D_MPI'])
    {'SPMD': None, 'NP': '4', '_MPI': None}
    """
    defines: dict[str, str | None] = {}
    for raw in raw_defines or []:
        token = raw.strip()
        if not token:
            continue
        if token.startswith("-D"):
            token = token[2:]
        if "=" in token:
            name, value = token.split("=", 1)
            defines[name.strip()] = value.strip()
        else:
            defines[token] = None
    return defines


@dataclass
class _Region:
    """One open #if/#ifdef/#ifndef on the conditional-nesting stack."""

    parent_active: bool
    branch_active: bool
    branch_taken: bool
    seen_else: bool
    open_line: int
    open_directive: str


def _in_true_region(stack: list[_Region]) -> bool:
    return all(r.branch_active for r in stack)


def _to_python_expr(cpp_expr: str) -> str:
    """Map C-preprocessor operator spelling to Python's own."""
    expr = cpp_expr
    # defined(X) / defined X -> defined(X), kept as a Call node the AST
    # walker special-cases (its argument is never evaluated as a value).
    expr = re.sub(r"\bdefined\s*\(\s*([A-Za-z_]\w*)\s*\)", r"defined(\1)", expr)
    expr = re.sub(r"\bdefined\s+([A-Za-z_]\w*)", r"defined(\1)", expr)
    expr = expr.replace("&&", " and ").replace("||", " or ")
    # '!' (not '!=') -> ' not '. CAM_CONFIG_OPTS-derived #if expressions
    # are always bare boolean/numeric exprs, never string literals, so a
    # blanket negative lookahead is sufficient here.
    expr = re.sub(r"!(?!=)", " not ", expr)
    return expr


def _maybe_int(value: str) -> object:
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _coerce_numeric_pair(left: object, right: object) -> tuple[object, object]:
    """Coerce both sides to int for a numeric comparison when possible.

    Deliberate departure from capgen-v1's own Eq/NotEq handling (see module
    docstring) -- a string-valued define ('4') would otherwise never equal
    an integer literal (4).
    """
    if isinstance(left, str) and isinstance(right, int):
        coerced = _maybe_int(left)
        if isinstance(coerced, int):
            return coerced, right
    if isinstance(right, str) and isinstance(left, int):
        coerced = _maybe_int(right)
        if isinstance(coerced, int):
            return left, coerced
    return left, right


class _RestrictedEval(ast.NodeVisitor):
    """Evaluate a restricted subset of Python AST nodes for #if/#elif.

    Only BoolOp, UnaryOp(Not), Compare, Call (only ``defined``/
    ``notdefined``), Name, and Constant are allowed -- anything else raises
    ValueError. Never uses eval()/exec().
    """

    def __init__(self, defines: dict[str, str | None], filename: str, line_no: int):
        self.defines = defines
        self.filename = filename
        self.line_no = line_no

    def _error(self, msg: str) -> None:
        raise ValueError(f"{self.filename}:{self.line_no}: {msg}")

    def visit(self, node):
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, None)
        if visitor is None:
            self._error(
                "unsupported expression in #if/#elif: "
                f"{ast.dump(node, include_attributes=False)}"
            )
        return visitor(node)

    def visit_Expression(self, node):
        return self.visit(node.body)

    def visit_BoolOp(self, node):
        values = [self.visit(v) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
        self._error("unsupported boolean operator")

    def visit_UnaryOp(self, node):
        if isinstance(node.op, ast.Not):
            return not self.visit(node.operand)
        self._error("unsupported unary operator (only 'not'/'!' allowed)")

    def visit_Compare(self, node):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            self._error("chained comparisons are not supported in #if/#elif")
        left = self._value(node.left)
        right = self._value(node.comparators[0])
        left, right = _coerce_numeric_pair(left, right)
        op = node.ops[0]
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
        self._error("unsupported comparison operator")

    def visit_Call(self, node):
        if not isinstance(node.func, ast.Name) or node.func.id not in (
            "defined",
            "notdefined",
        ):
            self._error("only 'defined(X)' is allowed as a function call")
        if len(node.args) != 1 or not isinstance(node.args[0], ast.Name):
            self._error("defined() takes exactly one bare identifier")
        is_defined = node.args[0].id in self.defines
        return is_defined if node.func.id == "defined" else not is_defined

    def visit_Name(self, node):
        return self._value(node)

    def visit_Constant(self, node):
        return self._value(node)

    def _value(self, node) -> object:
        """Return the runtime value of a Name/Constant/Call leaf node."""
        if isinstance(node, ast.Name):
            if node.id in self.defines:
                raw = self.defines[node.id]
                # A bare '-DSYM' (no '=VALUE') resolves to 1 when used as a
                # value -- 'defined(SYM)'/'#ifdef SYM' are unaffected (they
                # only test dict membership, never this value).
                return 1 if raw is None else _maybe_int(raw)
            # Real CPP rule: an undefined identifier used as a bare value
            # is replaced by 0 (see module docstring departure #1).
            return 0
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Call):
            return self.visit_Call(node)
        if isinstance(node, (ast.BoolOp, ast.UnaryOp, ast.Compare)):
            return self.visit(node)
        self._error(
            "unsupported expression in #if/#elif: "
            f"{ast.dump(node, include_attributes=False)}"
        )


def _eval_condition(
    cpp_expr: str, defines: dict[str, str | None], filename: str, line_no: int
) -> bool:
    python_expr = _to_python_expr(cpp_expr)
    try:
        tree = ast.parse(python_expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(
            f"{filename}:{line_no}: malformed #if/#elif expression "
            f"{cpp_expr!r}: {exc}"
        ) from None
    return bool(_RestrictedEval(defines, filename, line_no).visit(tree))


def preprocess_fortran_source(
    source: str, filename: str, defines: dict[str, str | None] | None
) -> str:
    """Apply #ifdef/#ifndef/#if/#elif/#else/#endif/#define/#undef to *source*.

    Returns a copy of *source* with the same number of lines, every
    excluded line blanked (never deleted, so line numbers stay accurate for
    fparser2's own line-number-based diagnostics). Does not mutate the
    caller's ``defines`` dict -- ``#define``/``#undef`` only affect a local
    copy.

    Raises ``ValueError(f"{filename}:{line_no}: ...")`` on malformed
    nesting (stray ``#else``/``#endif``/``#elif``, duplicate ``#else``,
    unterminated ``#ifdef``/``#if``) or a malformed ``#if``/``#elif``
    expression.
    """
    local_defines = dict(defines or {})
    stack: list[_Region] = []
    out_lines: list[str] = []

    for line_no, line in enumerate(source.splitlines(), start=1):
        match = _DIRECTIVE_RE.match(line)
        if match is None:
            out_lines.append(line if _in_true_region(stack) else "")
            continue

        keyword, rest = match.group(1), match.group(2).strip()
        parent_active = _in_true_region(stack)

        if keyword in ("ifdef", "ifndef"):
            symbol = rest.split()[0] if rest else ""
            if not symbol:
                raise ValueError(f"{filename}:{line_no}: '#{keyword}' with no symbol")
            is_defined = symbol in local_defines
            wants = is_defined if keyword == "ifdef" else not is_defined
            branch_active = parent_active and wants
            stack.append(
                _Region(
                    parent_active=parent_active,
                    branch_active=branch_active,
                    branch_taken=branch_active,
                    seen_else=False,
                    open_line=line_no,
                    open_directive=line.strip(),
                )
            )
        elif keyword == "if":
            branch_active = (
                _eval_condition(rest, local_defines, filename, line_no)
                if parent_active
                else False
            )
            stack.append(
                _Region(
                    parent_active=parent_active,
                    branch_active=branch_active,
                    branch_taken=branch_active,
                    seen_else=False,
                    open_line=line_no,
                    open_directive=line.strip(),
                )
            )
        elif keyword == "elif":
            if not stack:
                raise ValueError(f"{filename}:{line_no}: '#elif' with no matching '#if'")
            top = stack[-1]
            if top.seen_else:
                raise ValueError(f"{filename}:{line_no}: '#elif' after '#else'")
            grandparent_active = _in_true_region(stack[:-1])
            if top.branch_taken or not grandparent_active:
                top.branch_active = False
            else:
                top.branch_active = _eval_condition(
                    rest, local_defines, filename, line_no
                )
                if top.branch_active:
                    top.branch_taken = True
        elif keyword == "else":
            if not stack:
                raise ValueError(f"{filename}:{line_no}: '#else' with no matching '#if'")
            top = stack[-1]
            if top.seen_else:
                raise ValueError(f"{filename}:{line_no}: duplicate '#else'")
            top.seen_else = True
            grandparent_active = _in_true_region(stack[:-1])
            top.branch_active = grandparent_active and not top.branch_taken
            if top.branch_active:
                top.branch_taken = True
        elif keyword == "endif":
            if not stack:
                raise ValueError(f"{filename}:{line_no}: '#endif' with no matching '#if'")
            stack.pop()
        elif keyword == "define":
            parts = rest.split(None, 1)
            if not parts:
                raise ValueError(f"{filename}:{line_no}: '#define' with no symbol")
            name = parts[0]
            value = parts[1].strip() if len(parts) > 1 else None
            if _in_true_region(stack):
                local_defines[name] = value
        elif keyword == "undef":
            name = rest.split()[0] if rest else ""
            if not name:
                raise ValueError(f"{filename}:{line_no}: '#undef' with no symbol")
            if _in_true_region(stack):
                local_defines.pop(name, None)

        out_lines.append("")  # the directive line itself is always blanked

    if stack:
        top = stack[-1]
        raise ValueError(
            f"{filename}: unterminated '{top.open_directive}' opened at line "
            f"{top.open_line} (missing #endif)"
        )

    return "\n".join(out_lines)
