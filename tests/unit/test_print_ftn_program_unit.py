"""Fortran printing of a main program unit (ccpp_utils.ProgramOp) and the
pieces a generated test driver needs from the printer
(scheme-io-capture-driver-as-ir): static-shape local arrays, keyword
arguments in a call statement, and comment/blank lines."""

import io

from xdsl.dialects import arith, builtin, func, llvm, memref
from xdsl.dialects.builtin import StringAttr, i8, i32
from xdsl.ir import Block, Region

from xdsl_ccpp.backend.print_ftn import print_fortran_unit, print_to_ftn
from xdsl_ccpp.dialects.ccpp_utils import (
    AssignOp,
    BlankLineOp,
    CallStatementOp,
    CommentOp,
    KeywordArgExprOp,
    PrintStmtOp,
    ProgramOp,
    RealKindType,
    StringLiteralExprOp,
    VarRefExprOp,
)
from xdsl_ccpp.util.ccpp_conventions import mark_allocatable_local, name_local


def _external(name: str, module: str):
    decl = func.FuncOp.external(name, [], [])
    decl.attributes["module"] = StringAttr(module)
    return decl


def _use_stub(name: str, module: str):
    glob = llvm.GlobalOp(llvm.LLVMArrayType.from_size_and_type(1, i8), name, "external")
    glob.attributes["module"] = StringAttr(module)
    return glob


def _program(body_ops: list, extra_decls: "list | None" = None) -> ProgramOp:
    main = func.FuncOp("test_s_main", ((), ()), Region(Block([*body_ops, func.ReturnOp()])))
    decls = [_external("scheme_run", "s"), _use_stub("kind_phys", "ccpp_kinds")]
    return ProgramOp("test_s", "test_s_main", decls + (extra_decls or []) + [main])


def _text(unit) -> str:
    out = io.StringIO()
    print_fortran_unit(unit, out)
    return out.getvalue()


def test_program_unit_layout():
    n_failed = memref.AllocaOp.get(i32, shape=[])
    name_local(n_failed, "n_failed")
    text = _text(_program([
        n_failed,
        AssignOp(lhs_op=VarRefExprOp("n_failed", result_type=i32),
                 rhs_op=arith.ConstantOp.from_int_and_width(0, 32)),
    ]))
    lines = text.splitlines()
    assert lines[0] == "program test_s"
    assert lines[-1] == "end program test_s"
    assert "  use ccpp_kinds, only: kind_phys" in lines
    assert "  use s, only: scheme_run" in lines
    assert lines.index("  implicit none") < lines.index("  call test_s_main()") < lines.index("CONTAINS")
    assert "  subroutine test_s_main()" in lines
    assert "    integer :: n_failed" in lines
    assert "    n_failed = 0" in lines
    # A program has no module-only parts.
    assert "private" not in text and "public" not in text and "module" not in text


def test_program_gets_a_file_header_in_print_to_ftn():
    prog = builtin.ModuleOp([_program([])])
    out = io.StringIO()
    print_to_ftn(prog, out)
    assert out.getvalue().startswith("// FILE: test_s.F90\nprogram test_s\n")


def test_static_shape_and_kind_allocatable_locals():
    extents = memref.AllocaOp.get(i32, shape=[3])
    name_local(extents, "extents3")
    x = memref.AllocaOp.get(RealKindType("pumas_r8"), shape=[0, 0])
    mark_allocatable_local(x, "x")
    text = _text(_program([extents, x], [_use_stub("pumas_r8", "ccpp_kinds")]))
    assert "    integer :: extents3(3)" in text
    assert "    real(kind=pumas_r8), allocatable :: x(:, :)" in text
    assert "  use ccpp_kinds, only: pumas_r8" in text


def test_keyword_arguments_in_a_call_statement():
    text = _text(_program([CallStatementOp("scheme_run", arg_ops=[
        KeywordArgExprOp("ncol", VarRefExprOp("ncol")),
        KeywordArgExprOp("errmsg", VarRefExprOp("errmsg")),
    ])]))
    assert "    call scheme_run(ncol=ncol, errmsg=errmsg)" in text


def test_comment_lines_are_never_split():
    """A long comment with commas stays whole: the splitter breaks at
    commas, which would make the rest of the comment code."""
    long_comment = "replays " + ", ".join(f"phase_{i}" for i in range(30))
    text = _text(_program([CommentOp([long_comment, "second line"]), BlankLineOp(),
                           PrintStmtOp([StringLiteralExprOp("done")])]))
    assert f"    ! {long_comment}\n    ! second line\n\n" in text
    assert "    write(*,*) 'done'" in text
