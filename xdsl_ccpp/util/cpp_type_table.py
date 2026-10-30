"""Shared base-kind/width/rank/intent -> C-interop type decision table.

Both the chost (C++-host) BIND(C) cap generator
(`cpp_interop.py`'s `_chost_arg_type`, reading a resolved `ChostArgInfo`
descriptor) and the regular Fortran-host C header printer
(`print_cpp_header.py`'s `_c_param_type`, reading an MLIR type directly)
solve the same underlying problem for real/int scalars and arrays -- how a
base kind + width + rank + intent crosses the C interface -- from two
structurally different inputs. This is the one shared core both adapt
onto, so a future numeric type-mapping fix lands in one place instead of
needing to be applied (or missed) twice independently (BACKLOG.md's
`cpp-type-table-unify`).

The answer is an MLIR type, not C++ text: the element type itself (passed
by value), a memref (passed by pointer), or a `ReadOnlyType` around a
memref (a read-only pointer). `print_cpp_header.py`'s `cpp_type_name`
spells it.

Each caller keeps its own handling for everything this table doesn't
cover (character buffers, bool/logical, and chost's own
ncol/nz/errflg/scheme-name special cases) -- those aren't duplicated
logic between the two files, they're genuinely different problems each
one solves only for its own domain.
"""

from xdsl.dialects.builtin import DYNAMIC_INDEX, MemRefType, f32, f64, i32

from xdsl_ccpp.dialects.ccpp_utils import ReadOnlyType


def c_numeric_type(
    *, kind: str, width: int, rank: int, intent: "str | None",
    const_in_arrays: bool = True,
):
    """Map a real/int base kind + width + rank + intent to a C-interop type.

    kind: "int" or "real". width: bit width (32 or 64), meaningful only
    for "real" ("int" is always C `int`, i32, matching this codebase's
    existing convention of never emitting `int32_t`/`int64_t`). rank: 0
    for scalar, >0 for array.

    A scalar (rank == 0) with intent "in" passes by value, matching the
    Fortran BIND(C) VALUE attribute. Every other case -- any array, or a
    non-"in" scalar -- passes by pointer. `const_in_arrays` controls
    whether an intent(in) *array* is additionally read-only: the two
    callers have each independently settled this differently
    (`_chost_arg_type` does; `_c_param_type` doesn't) -- this parameter
    keeps that one real divergence explicit and visible in a single shared
    place instead of it being silently re-decided twice.
    """
    base = i32 if kind == "int" else (f32 if width == 32 else f64)
    if rank == 0 and intent == "in":
        return base
    pointer = MemRefType(base, [DYNAMIC_INDEX] if rank > 0 else [])
    if intent == "in" and const_in_arrays:
        return ReadOnlyType(pointer)
    return pointer
