"""Shared base-kind/width/rank/intent -> C++ type-string decision table.

Both the chost (C++-host) BIND(C) cap generator
(`cpp_interop.py`'s `_chost_cpp_type`, reading a resolved `ChostArgInfo`
descriptor) and the regular Fortran-host C header printer
(`print_cpp_header.py`'s `_cpp_type`, reading an MLIR type directly) solve
the same underlying problem for real/int scalars and arrays -- map a base
kind + width + rank + intent to a C++ type string -- from two structurally
different inputs. This is the one shared core both adapt onto, so a
future numeric type-mapping fix lands in one place instead of needing to
be applied (or missed) twice independently (BACKLOG.md's
`cpp-type-table-unify`).

Each caller keeps its own handling for everything this table doesn't
cover (character buffers, bool/logical, and chost's own
ncol/nz/errflg/scheme-name special cases) -- those aren't duplicated
logic between the two files, they're genuinely different problems each
one solves only for its own domain.
"""


def cpp_numeric_type(
    *, kind: str, width: int, rank: int, intent: "str | None",
    const_in_arrays: bool = True,
) -> str:
    """Map a real/int base kind + width + rank + intent to a C++ type.

    kind: "int" or "real". width: bit width (32 or 64), meaningful only
    for "real" ("int" is always plain C `int`, matching this codebase's
    existing convention of never emitting `int32_t`/`int64_t`). rank: 0
    for scalar, >0 for array.

    A scalar (rank == 0) with intent "in" passes by value, matching the
    Fortran BIND(C) VALUE attribute. Every other case -- any array, or a
    non-"in" scalar -- passes by pointer. `const_in_arrays` controls
    whether an intent(in) *array* additionally gets a `const` pointer:
    the two callers have each independently settled this differently
    (`_chost_cpp_type` does; `_cpp_type` doesn't) -- this parameter keeps
    that one real divergence explicit and visible in a single shared
    place instead of it being silently re-decided twice.
    """
    base = "int" if kind == "int" else ("float" if width == 32 else "double")
    if rank == 0 and intent == "in":
        return base
    if intent == "in" and const_in_arrays:
        return f"const {base}*"
    return f"{base}*"
