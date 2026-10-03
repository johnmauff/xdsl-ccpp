"""Shared operator-precedence/parenthesization mechanism for the
language-neutral expression IR (``lang-neutral-expr-ir``).

Both ``print_ftn.py``'s ``print_expr`` and ``print_cpp_header.py``'s
``expr_to_cpp_str`` render the *same* IR tree (``arith``/``math`` binary
ops plus the new ``ccpp_utils`` expression ops) into two different
textual languages. Precedence is a property of the operator itself, not
of its spelling in either language, so the level/associativity table
below (``OP_PRECEDENCE``) is shared between both printers -- only the
operator *token* tables (``_binops``/``_cmp_ops`` in ``print_ftn.py``,
and their C++ siblings in ``print_cpp_header.py``) differ per language.

Confirmed before writing this module: zero precedence/parenthesization
logic exists anywhere in this codebase's printers, or in xDSL's own
generic MLIR printer -- today's flat strings got correct parens "for
free" from the original hand-written source text they were extracted
from. This is new, from scratch.
"""

from xdsl.dialects import arith, math

# Atoms -- literals, references, calls, indexing, member access -- never
# need outer parens when used as a child of a binary/comparison op.
ATOM_LEVEL = 1000

# Precedence levels, highest binds tightest. The relative ordering of
# .or./.and./comparisons/+-/*//** is identical in Fortran and C++ even
# though the spellings differ (.and. vs &&, etc.) -- only the *level
# number* matters to parenthesize(), never the printed token.
LEVEL_OR = 10  # .or.  / ||
LEVEL_AND = 20  # .and. / &&
LEVEL_CMP = 30  # == /= < <= > >=  (relational ops don't chain in either language)
LEVEL_ADD = 40  # + -
LEVEL_MUL = 50  # * / %
LEVEL_POW = 60  # **  (right-associative)

# op.name -> (level, associativity). Ops absent from this table (every
# atom: ConstantOp, memref.LoadOp, StrCmpOp, TrimOp, and all of the new
# ccpp_utils expr-* ops) are ATOM_LEVEL/"none" via level_of()/assoc_of()'s
# own fallback -- they never need outer parens as a child, and never
# parenthesize their own children on associativity grounds.
OP_PRECEDENCE: dict[str, tuple[int, str]] = {
    arith.OrIOp.name: (LEVEL_OR, "left"),
    arith.AndIOp.name: (LEVEL_AND, "left"),
    arith.CmpiOp.name: (LEVEL_CMP, "none"),
    arith.CmpfOp.name: (LEVEL_CMP, "none"),
    arith.AddiOp.name: (LEVEL_ADD, "left"),
    arith.AddfOp.name: (LEVEL_ADD, "left"),
    arith.SubiOp.name: (LEVEL_ADD, "left"),
    arith.SubfOp.name: (LEVEL_ADD, "left"),
    arith.MuliOp.name: (LEVEL_MUL, "left"),
    arith.MulfOp.name: (LEVEL_MUL, "left"),
    arith.DivSIOp.name: (LEVEL_MUL, "left"),
    arith.DivUIOp.name: (LEVEL_MUL, "left"),
    arith.DivfOp.name: (LEVEL_MUL, "left"),
    math.PowFOp.name: (LEVEL_POW, "right"),
    math.IPowIOp.name: (LEVEL_POW, "right"),
    math.FPowIOp.name: (LEVEL_POW, "right"),
}


def level_of(op) -> int:
    """Return op's precedence level, or ATOM_LEVEL if it has none."""
    entry = OP_PRECEDENCE.get(op.name)
    return entry[0] if entry is not None else ATOM_LEVEL


def assoc_of(op) -> str:
    """Return op's associativity ("left"/"right"/"none"), or "none" if
    op has no precedence entry (irrelevant for an atom -- it never
    parenthesizes its own children on associativity grounds)."""
    entry = OP_PRECEDENCE.get(op.name)
    return entry[1] if entry is not None else "none"


def parenthesize(
    child_text: str, child_level: int, my_level: int, side: str, assoc: str
) -> str:
    """side: 'lhs'|'rhs'; assoc: 'left'|'right'|'none' (my own op).

    Parenthesize if the child binds looser, or binds at the same level
    but sits on the 'wrong' side for my associativity ('none'
    parenthesizes any same-level child on either side -- Fortran
    relational ops don't chain).
    """
    needs_parens = child_level < my_level or (
        child_level == my_level
        and (
            assoc == "none"
            or (assoc == "left" and side == "rhs")
            or (assoc == "right" and side == "lhs")
        )
    )
    return f"({child_text})" if needs_parens else child_text
