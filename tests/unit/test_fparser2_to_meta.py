"""Unit tests for fparser2_to_meta — source extraction via fparser2.

Tests the full pipeline from Fortran source text to CCPP IR, then validates
the result using compare_modules from validate_fir.
"""

import pytest

pytest.importorskip("fparser", reason="fparser not installed")

from xdsl_ccpp.transforms.fparser2_to_meta import build_meta_module_from_source
from xdsl_ccpp.transforms.validate_fir import Mismatch, compare_modules
from xdsl_ccpp.dialects.ccpp import ArgumentOp, ArgumentTableOp
from xdsl.dialects.builtin import ModuleOp


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_table(table_name, args):
    ops = [ArgumentOp(name, attrs["type"], attrs) for name, attrs in args]
    return ArgumentTableOp(table_name, "scheme", ops)


def _real(intent, dims="()"):
    return {"type": "real", "intent": intent, "dimensions": dims}


def _int(intent):
    return {"type": "integer", "intent": intent, "dimensions": "()"}


# ── extraction tests ──────────────────────────────────────────────────────────

def test_extracts_subroutine_name():
    src = """
module mymod
contains
  subroutine mymod_run(errflg)
    integer, intent(out) :: errflg
  end subroutine
end module
"""
    mod = build_meta_module_from_source(src)
    tables = {op.table_name.data for op in mod.body.block.ops
              if isinstance(op, ArgumentTableOp.__class__)}
    # arg tables are inside table_properties ops — use compare_modules helper
    from xdsl_ccpp.transforms.validate_fir import _collect_arg_tables
    tbls = _collect_arg_tables(mod)
    assert "mymod_run" in tbls


def test_extracts_scalar_integer():
    src = """
module m
contains
  subroutine m_run(errflg)
    integer, intent(out) :: errflg
  end subroutine
end module
"""
    mod = build_meta_module_from_source(src)
    from xdsl_ccpp.transforms.validate_fir import _collect_arg_tables
    arg = _collect_arg_tables(mod)["m_run"].body.block.ops.__iter__().__next__()
    assert arg.arg_type.data == "integer"
    assert arg.intent.data == "out"
    assert (arg.dimensions.data if arg.dimensions else 0) == 0


def test_extracts_2d_real_array():
    src = """
module m
contains
  subroutine m_run(temp)
    real, intent(inout) :: temp(:, :)
  end subroutine
end module
"""
    mod = build_meta_module_from_source(src)
    from xdsl_ccpp.transforms.validate_fir import _collect_arg_tables
    arg = _collect_arg_tables(mod)["m_run"].body.block.ops.__iter__().__next__()
    assert arg.arg_type.data == "real"
    assert arg.dimensions.data == 2
    assert arg.intent.data == "inout"


def test_extracts_optional_flag():
    src = """
module m
contains
  subroutine m_run(qv)
    real, optional, intent(inout) :: qv(:)
  end subroutine
end module
"""
    mod = build_meta_module_from_source(src)
    from xdsl_ccpp.transforms.validate_fir import _collect_arg_tables
    arg = _collect_arg_tables(mod)["m_run"].body.block.ops.__iter__().__next__()
    assert arg.optional is not None


def test_dimension_attribute_style():
    src = """
module m
contains
  subroutine m_run(temp)
    real, dimension(:, :), intent(in) :: temp
  end subroutine
end module
"""
    mod = build_meta_module_from_source(src)
    from xdsl_ccpp.transforms.validate_fir import _collect_arg_tables
    arg = _collect_arg_tables(mod)["m_run"].body.block.ops.__iter__().__next__()
    assert arg.dimensions.data == 2


def test_multiple_subroutines():
    src = """
module m
contains
  subroutine m_init(errflg)
    integer, intent(out) :: errflg
  end subroutine
  subroutine m_run(temp, errflg)
    real, intent(inout) :: temp(:)
    integer, intent(out) :: errflg
  end subroutine
end module
"""
    mod = build_meta_module_from_source(src)
    from xdsl_ccpp.transforms.validate_fir import _collect_arg_tables
    tbls = _collect_arg_tables(mod)
    assert "m_init" in tbls
    assert "m_run" in tbls


# ── round-trip comparison against manually built IR ──────────────────────────

def test_roundtrip_no_mismatches():
    src = """
module scheme
contains
  subroutine scheme_run(temp, errflg)
    real, intent(inout) :: temp(:, :)
    integer, intent(out) :: errflg
  end subroutine
end module
"""
    fparser_mod = build_meta_module_from_source(src)
    meta_mod = ModuleOp([
        _make_table("scheme_run", [
            ("temp", _real("inout", "(ncols, nlev)")),
            ("errflg", _int("out")),
        ])
    ])
    assert compare_modules(meta_mod, fparser_mod) == []


def test_roundtrip_detects_type_mismatch():
    src = """
module scheme
contains
  subroutine scheme_run(flag)
    real, intent(out) :: flag
  end subroutine
end module
"""
    fparser_mod = build_meta_module_from_source(src)
    meta_mod = ModuleOp([
        _make_table("scheme_run", [("flag", _int("out"))])
    ])
    mm = compare_modules(meta_mod, fparser_mod)
    assert any(m.field == "type" for m in mm)


def test_roundtrip_detects_rank_mismatch():
    src = """
module scheme
contains
  subroutine scheme_run(temp)
    real, intent(inout) :: temp(:)
  end subroutine
end module
"""
    fparser_mod = build_meta_module_from_source(src)
    meta_mod = ModuleOp([
        _make_table("scheme_run", [("temp", _real("inout", "(ncols, nlev)"))])
    ])
    mm = compare_modules(meta_mod, fparser_mod)
    assert any(m.field == "rank" for m in mm)


def test_roundtrip_detects_optional_mismatch():
    src = """
module scheme
contains
  subroutine scheme_run(qv)
    real, intent(inout) :: qv(:)
  end subroutine
end module
"""
    fparser_mod = build_meta_module_from_source(src)
    meta_mod = ModuleOp([
        _make_table("scheme_run", [
            ("qv", {"type": "real", "intent": "inout",
                    "dimensions": "(ncols)", "optional": "True"})
        ])
    ])
    mm = compare_modules(meta_mod, fparser_mod)
    assert any(m.field == "optional" for m in mm)


# ── kind extraction and comparison ───────────────────────────────────────────

def test_extracts_kind_positional():
    src = """
module m
contains
  subroutine m_run(temp)
    real(kind_phys), intent(inout) :: temp
  end subroutine
end module
"""
    mod = build_meta_module_from_source(src)
    from xdsl_ccpp.transforms.validate_fir import _collect_arg_tables
    arg = next(iter(_collect_arg_tables(mod)["m_run"].body.block.ops))
    assert arg.kind is not None
    assert arg.kind.data == "kind_phys"


def test_extracts_kind_explicit():
    src = """
module m
contains
  subroutine m_run(temp)
    real(KIND=kind_phys), intent(inout) :: temp
  end subroutine
end module
"""
    mod = build_meta_module_from_source(src)
    from xdsl_ccpp.transforms.validate_fir import _collect_arg_tables
    arg = next(iter(_collect_arg_tables(mod)["m_run"].body.block.ops))
    assert arg.kind is not None
    assert arg.kind.data == "kind_phys"


def test_no_kind_when_unspecified():
    src = """
module m
contains
  subroutine m_run(errflg)
    integer, intent(out) :: errflg
  end subroutine
end module
"""
    mod = build_meta_module_from_source(src)
    from xdsl_ccpp.transforms.validate_fir import _collect_arg_tables
    arg = next(iter(_collect_arg_tables(mod)["m_run"].body.block.ops))
    assert arg.kind is None


def test_roundtrip_detects_kind_mismatch():
    src = """
module scheme
contains
  subroutine scheme_run(temp)
    real(kind_phys), intent(inout) :: temp
  end subroutine
end module
"""
    fparser_mod = build_meta_module_from_source(src)
    meta_mod = ModuleOp([
        _make_table("scheme_run", [
            ("temp", {"type": "real", "intent": "inout", "kind": "kind_dyn"})
        ])
    ])
    mm = compare_modules(meta_mod, fparser_mod)
    assert any(m.field == "kind" for m in mm)


def test_roundtrip_no_kind_mismatch_when_matching():
    src = """
module scheme
contains
  subroutine scheme_run(temp)
    real(kind_phys), intent(inout) :: temp
  end subroutine
end module
"""
    fparser_mod = build_meta_module_from_source(src)
    meta_mod = ModuleOp([
        _make_table("scheme_run", [
            ("temp", {"type": "real", "intent": "inout", "kind": "kind_phys"})
        ])
    ])
    assert compare_modules(meta_mod, fparser_mod) == []


def test_extracts_ddt_type():
    src = """
module m
contains
  subroutine m_run(vmr)
    type(vmr_type), intent(inout) :: vmr
  end subroutine
end module
"""
    mod = build_meta_module_from_source(src)
    from xdsl_ccpp.transforms.validate_fir import _collect_arg_tables
    arg = next(iter(_collect_arg_tables(mod)["m_run"].body.block.ops))
    assert arg.arg_type.data == "vmr_type"


def test_roundtrip_ddt_no_mismatch():
    src = """
module scheme
contains
  subroutine scheme_run(vmr, errflg)
    type(vmr_type), intent(inout) :: vmr
    integer,        intent(out)   :: errflg
  end subroutine
end module
"""
    fparser_mod = build_meta_module_from_source(src)
    meta_mod = ModuleOp([
        _make_table("scheme_run", [
            ("vmr",    {"type": "vmr_type", "intent": "inout", "dimensions": "()"}),
            ("errflg", _int("out")),
        ])
    ])
    assert compare_modules(meta_mod, fparser_mod) == []


def test_roundtrip_ddt_type_mismatch():
    src = """
module scheme
contains
  subroutine scheme_run(state)
    type(wrong_type), intent(inout) :: state
  end subroutine
end module
"""
    fparser_mod = build_meta_module_from_source(src)
    meta_mod = ModuleOp([
        _make_table("scheme_run", [
            ("state", {"type": "correct_type", "intent": "inout", "dimensions": "()"}),
        ])
    ])
    mm = compare_modules(meta_mod, fparser_mod)
    assert any(m.field == "type" for m in mm)


def test_kind_not_compared_when_source_omits_it():
    # FIR backend leaves kind unset; we must not flag a mismatch
    src = """
module scheme
contains
  subroutine scheme_run(temp)
    real, intent(inout) :: temp
  end subroutine
end module
"""
    fparser_mod = build_meta_module_from_source(src)
    meta_mod = ModuleOp([
        _make_table("scheme_run", [
            ("temp", {"type": "real", "intent": "inout", "kind": "kind_phys"})
        ])
    ])
    # fparser2 extracted no kind → no mismatch even though .meta has kind
    assert compare_modules(meta_mod, fparser_mod) == []
