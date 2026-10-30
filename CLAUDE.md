# Instructions for agents working on xdsl-ccpp

## Build reusable IR, never target-language syntax

xdsl-ccpp is an IR-based compiler. The middle layer (`xdsl_ccpp/transforms/`,
`xdsl_ccpp/dialects/`) must build language-neutral IR; Fortran and C++ syntax belong
only in the backend printers (`xdsl_ccpp/backend/print_ftn.py`,
`xdsl_ccpp/backend/print_cpp_header.py`) and in the frontends that parse Fortran input.
Passes and verifiers can only reason about what is in ops, and one IR must print to more
than one language.

Do not hardcode language constructs in transforms:

- no raw-text statement ops;
- no syntax inside the string fields of typed ops: `AssignOp("x", ".true.")`,
  `"integer, intent(in) :: n"`, `"size(x)"`, `"n + 1"`, `"if (...) return"`,
  `"!$acc enter data ..."`, `"real(x, kind_phys)"`;
- no facts encoded in names (e.g. `__opt`/`__in` suffixes) -- use attributes
  (`arg_attrs`, op attributes).

Identifiers and message strings are data and are fine.

Instead, compose existing ops -- expressions: `VarRefExprOp`, `ValueExprOp`,
`CallExprOp`, `IndexExprOp`, `MemberAccessExprOp`, `StringLiteralExprOp`, `arith`
constants and operators; statements: `AssignOp(lhs_op=..., rhs_op=...)`, `scf.if`
(`_scf_if`), `ReturnStmtOp`, `ErrorExitOp`, `AllocateOp`, the `Acc*`/`Omp*` ops,
`func.FuncOp` with typed arguments and `arg_attrs`. If no op fits, add a small, reusable
op and its printer case rather than emitting text.

Before calling such work done, scan the string literals of `xdsl_ccpp/transforms/` for
target syntax (`::`, `intent(`, `.true.`, `/=`, statement keywords, intrinsic calls,
`!$`) instead of trusting a count of one op class.

Some Fortran and C++ syntax still appears as strings in `xdsl_ccpp/transforms/`. Each
known case is an open item in `BACKLOG.md`. Don't write new code that does this. If you
find a case that isn't in `BACKLOG.md`, add it there as a new item.
`tests/unit/test_ir_names_are_identifiers.py` checks the IR's naming properties.
