"""Parser for the expressions a ``.meta`` file can hold.

Two kinds, both written in standard-name space:

- an ``active`` property: a logical expression over standard names,
  integer and logical literals, e.g. ``(index_of_water_vapor_specific_humidity
  > 0)`` or ``flag_a .and. .not. flag_b``;
- a subscripted local name of a host variable, e.g.
  ``q(:,:,index_of_water_vapor_specific_humidity)``, where each subscript is
  ``:``, an integer literal or a standard name.

The parser is hand-written (tokenizer plus recursive descent) and returns
the small syntax tree below; it knows nothing about Fortran output. Errors
are MetaExprError, with the column of the offending token; the frontend
adds ``filename:line``.

Operator precedence, lowest first, as in Fortran: ``.eqv.``/``.neqv.``,
``.or.``, ``.and.``, ``.not.``, relational (non-associative).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class MetaExprError(ValueError):
    """A malformed ``.meta`` expression."""

    def __init__(self, message: str, text: str, column: int):
        self.column = column
        super().__init__(f"{message} at column {column + 1} of '{text}'")


# --- syntax tree --------------------------------------------------------


@dataclass(frozen=True)
class Name:
    """A standard name (stored lower-case: standard names are
    case-insensitive)."""

    std_name: str


@dataclass(frozen=True)
class IntLiteral:
    value: int


@dataclass(frozen=True)
class LogicalLiteral:
    value: bool


@dataclass(frozen=True)
class Not:
    operand: object


# Logical and relational operators, by the names Binary.op uses.
LOGICAL_OPS = ("and", "or", "eqv", "neqv")
RELATIONAL_OPS = ("eq", "ne", "lt", "le", "gt", "ge")


@dataclass(frozen=True)
class Binary:
    op: str  # one of LOGICAL_OPS or RELATIONAL_OPS
    lhs: object
    rhs: object


@dataclass(frozen=True)
class FullSlice:
    """A bare ``:`` subscript (the whole dimension)."""


@dataclass(frozen=True)
class SubscriptedName:
    """A local name with optional subscripts, e.g. ``q(:, :, <std name>)``.
    ``subscripts`` is empty for a plain name; each element is FullSlice,
    IntLiteral or Name."""

    name: str
    subscripts: tuple = ()


# --- tokenizer ----------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<dotop>\.[A-Za-z]+\.)
  | (?P<relop>==|/=|<=|>=|<|>)
  | (?P<int>[0-9]+)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<punct>[(),:])
    """,
    re.VERBOSE,
)

_DOT_OPS = {
    ".and.": "and", ".or.": "or", ".eqv.": "eqv", ".neqv.": "neqv", ".not.": "not",
    ".eq.": "eq", ".ne.": "ne", ".lt.": "lt", ".le.": "le", ".gt.": "gt", ".ge.": "ge",
    ".true.": "true", ".false.": "false",
}
_REL_SYMBOLS = {"==": "eq", "/=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}


@dataclass(frozen=True)
class _Token:
    kind: str  # "op", "int", "ident", "punct", "end"
    value: str
    column: int


def _tokenize(text: str) -> list[_Token]:
    tokens = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if m is None:
            raise MetaExprError(f"unexpected character {text[pos]!r}", text, pos)
        kind = m.lastgroup
        value = m.group()
        if kind == "dotop":
            op = _DOT_OPS.get(value.lower())
            if op is None:
                raise MetaExprError(f"unknown operator {value!r}", text, pos)
            tokens.append(_Token("op", op, pos))
        elif kind == "relop":
            tokens.append(_Token("op", _REL_SYMBOLS[value], pos))
        elif kind != "ws":
            tokens.append(_Token(kind, value, pos))
        pos = m.end()
    tokens.append(_Token("end", "", len(text)))
    return tokens


# --- parser -------------------------------------------------------------


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.tokens = _tokenize(text)
        self.pos = 0

    def peek(self) -> _Token:
        return self.tokens[self.pos]

    def advance(self) -> _Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def error(self, message: str, tok: _Token | None = None):
        tok = tok or self.peek()
        raise MetaExprError(message, self.text, tok.column)

    def expect_punct(self, value: str) -> None:
        tok = self.peek()
        if tok.kind != "punct" or tok.value != value:
            self.error(f"expected {value!r}")
        self.advance()

    def expect_end(self) -> None:
        if self.peek().kind != "end":
            self.error(f"unexpected {self.peek().value!r}")

    def at_op(self, *ops: str) -> bool:
        tok = self.peek()
        return tok.kind == "op" and tok.value in ops

    # expr := eqv
    def expr(self):
        return self.binary_level(("eqv", "neqv"), self.or_expr)

    def or_expr(self):
        return self.binary_level(("or",), self.and_expr)

    def and_expr(self):
        return self.binary_level(("and",), self.not_expr)

    def binary_level(self, ops, operand):
        lhs = operand()
        while self.at_op(*ops):
            op = self.advance().value
            lhs = Binary(op, lhs, operand())
        return lhs

    def not_expr(self):
        if self.at_op("not"):
            self.advance()
            return Not(self.not_expr())
        return self.relational()

    def relational(self):
        lhs = self.primary()
        if self.at_op(*RELATIONAL_OPS):
            op = self.advance().value
            rhs = self.primary()
            if self.at_op(*RELATIONAL_OPS):
                self.error("relational operators do not chain")
            return Binary(op, lhs, rhs)
        return lhs

    def primary(self):
        tok = self.peek()
        if tok.kind == "punct" and tok.value == "(":
            self.advance()
            inner = self.expr()
            self.expect_punct(")")
            return inner
        if tok.kind == "int":
            self.advance()
            return IntLiteral(int(tok.value))
        if tok.kind == "ident":
            self.advance()
            return Name(tok.value.lower())
        if tok.kind == "op" and tok.value in ("true", "false"):
            self.advance()
            return LogicalLiteral(tok.value == "true")
        if tok.kind == "end":
            self.error("expression ends early")
        self.error(f"unexpected {tok.value!r}")

    # subscripted_name := ident [ '(' subscript { ',' subscript } ')' ]
    def subscripted_name(self) -> SubscriptedName:
        tok = self.peek()
        if tok.kind != "ident":
            self.error("expected a name")
        name = self.advance().value
        subscripts = []
        if self.peek().kind == "punct" and self.peek().value == "(":
            self.advance()
            subscripts.append(self.subscript())
            while self.peek().kind == "punct" and self.peek().value == ",":
                self.advance()
                subscripts.append(self.subscript())
            self.expect_punct(")")
        return SubscriptedName(name, tuple(subscripts))

    def subscript(self):
        tok = self.peek()
        if tok.kind == "punct" and tok.value == ":":
            self.advance()
            return FullSlice()
        if tok.kind == "int":
            self.advance()
            return IntLiteral(int(tok.value))
        if tok.kind == "ident":
            self.advance()
            return Name(tok.value.lower())
        self.error("expected ':', an integer or a standard name as a subscript")


def parse_active_expr(text: str):
    """Parse an ``active`` property into a syntax tree."""
    parser = _Parser(text)
    tree = parser.expr()
    parser.expect_end()
    return tree


def parse_local_name(text: str) -> SubscriptedName:
    """Parse a variable's local name, which a host table may subscript."""
    parser = _Parser(text)
    tree = parser.subscripted_name()
    parser.expect_end()
    return tree


def standard_names(tree) -> list[str]:
    """The standard names a syntax tree references, in order, once each."""
    found: list[str] = []

    def walk(node):
        if isinstance(node, Name):
            if node.std_name not in found:
                found.append(node.std_name)
        elif isinstance(node, Not):
            walk(node.operand)
        elif isinstance(node, Binary):
            walk(node.lhs)
            walk(node.rhs)
        elif isinstance(node, SubscriptedName):
            for sub in node.subscripts:
                walk(sub)

    walk(tree)
    return found
