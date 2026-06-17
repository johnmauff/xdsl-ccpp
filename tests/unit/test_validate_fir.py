"""Unit tests for validate_fir comparison logic.

All tests build CCPP IR programmatically — no Flang or .meta file parsing
required.  This makes the suite fast and runnable without any external tools.
"""

import pytest

from xdsl.dialects.builtin import ModuleOp

from xdsl_ccpp.dialects.ccpp import ArgumentOp, ArgumentTableOp
from xdsl_ccpp.transforms.validate_fir import (
    Mismatch,
    check_dimension_names,
    collect_standard_names,
    compare_arg_tables,
    compare_modules,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_table(table_name: str, args: list[tuple[str, dict]]) -> ArgumentTableOp:
    """Build an ArgumentTableOp from (arg_name, attrs_dict) pairs."""
    ops = [ArgumentOp(name, attrs["type"], attrs) for name, attrs in args]
    return ArgumentTableOp(table_name, "scheme", ops)


def _real(intent: str, dims: str = "()") -> dict:
    return {"type": "real", "intent": intent, "dimensions": dims}


def _int(intent: str) -> dict:
    return {"type": "integer", "intent": intent, "dimensions": "()"}


def _char(intent: str) -> dict:
    return {"type": "character", "intent": intent, "dimensions": "()"}


# ── compare_arg_tables ────────────────────────────────────────────────────────

def test_identical_tables_no_mismatches():
    args = [("temp", _real("inout", "(ncols, nlev)")), ("errflg", _int("out"))]
    meta = _make_table("scheme_run", args)
    fir  = _make_table("scheme_run", args)
    assert compare_arg_tables(meta, fir) == []


def test_type_mismatch():
    meta = _make_table("scheme_run", [("flag", _int("out"))])
    fir  = _make_table("scheme_run", [("flag", _real("out"))])
    mm = compare_arg_tables(meta, fir)
    assert len(mm) == 1
    assert mm[0].field == "type"
    assert mm[0].meta_value == "integer"
    assert mm[0].fir_value == "real"


def test_rank_mismatch():
    meta = _make_table("scheme_run", [("arr", _real("inout", "(ncols, nlev)"))])
    fir  = _make_table("scheme_run", [("arr", _real("inout", "(ncols)"))])
    mm = compare_arg_tables(meta, fir)
    assert len(mm) == 1
    assert mm[0].field == "rank"
    assert mm[0].meta_value == "2"
    assert mm[0].fir_value == "1"


def test_scalar_vs_array_rank_mismatch():
    meta = _make_table("scheme_run", [("t", _real("inout"))])           # rank 0
    fir  = _make_table("scheme_run", [("t", _real("inout", "(ncols)"))])  # rank 1
    mm = compare_arg_tables(meta, fir)
    assert len(mm) == 1
    assert mm[0].field == "rank"
    assert mm[0].meta_value == "0"
    assert mm[0].fir_value == "1"


def test_intent_mismatch():
    meta = _make_table("scheme_run", [("temp", _real("in"))])
    fir  = _make_table("scheme_run", [("temp", _real("inout"))])
    mm = compare_arg_tables(meta, fir)
    assert len(mm) == 1
    assert mm[0].field == "intent"
    assert mm[0].meta_value == "in"
    assert mm[0].fir_value == "inout"


def test_intent_only_in_meta_no_mismatch():
    """If FIR omits intent (e.g. for internal args), do not flag a mismatch."""
    meta = _make_table("scheme_run", [("temp", _real("in"))])
    fir_attrs = {"type": "real", "dimensions": "()"}   # no intent key
    fir  = _make_table("scheme_run", [("temp", fir_attrs)])
    assert compare_arg_tables(meta, fir) == []


def test_optional_mismatch_meta_has_optional():
    meta_attrs = {"type": "real", "intent": "inout", "dimensions": "(ncols)", "optional": "True"}
    fir_attrs  = {"type": "real", "intent": "inout", "dimensions": "(ncols)"}
    meta = _make_table("scheme_run", [("qv", meta_attrs)])
    fir  = _make_table("scheme_run", [("qv", fir_attrs)])
    mm = compare_arg_tables(meta, fir)
    assert len(mm) == 1
    assert mm[0].field == "optional"
    assert mm[0].meta_value == "True"
    assert mm[0].fir_value == "False"


def test_optional_mismatch_fir_has_optional():
    meta_attrs = {"type": "real", "intent": "inout", "dimensions": "(ncols)"}
    fir_attrs  = {"type": "real", "intent": "inout", "dimensions": "(ncols)", "optional": "True"}
    meta = _make_table("scheme_run", [("qv", meta_attrs)])
    fir  = _make_table("scheme_run", [("qv", fir_attrs)])
    mm = compare_arg_tables(meta, fir)
    assert len(mm) == 1
    assert mm[0].field == "optional"
    assert mm[0].meta_value == "False"
    assert mm[0].fir_value == "True"


def test_both_optional_no_mismatch():
    attrs = {"type": "real", "intent": "inout", "dimensions": "(ncols)", "optional": "True"}
    meta = _make_table("scheme_run", [("qv", attrs)])
    fir  = _make_table("scheme_run", [("qv", attrs)])
    assert compare_arg_tables(meta, fir) == []


def test_extra_arg_in_meta():
    meta = _make_table("scheme_run", [
        ("temp", _real("inout", "(ncols)")),
        ("ghost", _int("in")),
    ])
    fir = _make_table("scheme_run", [("temp", _real("inout", "(ncols)"))])
    mm = compare_arg_tables(meta, fir)
    assert len(mm) == 1
    assert mm[0].field == "extra_in_meta"
    assert mm[0].arg_name == "ghost"


def test_extra_arg_in_fir():
    meta = _make_table("scheme_run", [("temp", _real("inout", "(ncols)"))])
    fir  = _make_table("scheme_run", [
        ("temp", _real("inout", "(ncols)")),
        ("mystery", _int("in")),
    ])
    mm = compare_arg_tables(meta, fir)
    assert len(mm) == 1
    assert mm[0].field == "extra_in_fir"
    assert mm[0].arg_name == "mystery"


def test_multiple_mismatches_reported():
    meta = _make_table("scheme_run", [
        ("a", _real("in")),
        ("b", _int("out")),
    ])
    fir = _make_table("scheme_run", [
        ("a", _real("inout")),   # intent wrong
        ("b", _real("out")),     # type wrong
    ])
    mm = compare_arg_tables(meta, fir)
    fields = {m.field for m in mm}
    assert "intent" in fields
    assert "type" in fields


# ── compare_modules ───────────────────────────────────────────────────────────

def test_compare_modules_matching():
    args = [("temp", _real("inout", "(ncols)")), ("errflg", _int("out"))]
    meta_mod = ModuleOp([_make_table("scheme_run", args)])
    fir_mod  = ModuleOp([_make_table("scheme_run", args)])
    assert compare_modules(meta_mod, fir_mod) == []


def test_compare_modules_table_only_in_meta_skipped():
    """Tables without a FIR counterpart (host tables etc.) are silently skipped."""
    args = [("temp", _real("inout", "(ncols)"))]
    meta_mod = ModuleOp([
        _make_table("scheme_run", args),
        _make_table("host_module", [("psurf", _real("in"))]),
    ])
    fir_mod = ModuleOp([_make_table("scheme_run", args)])
    assert compare_modules(meta_mod, fir_mod) == []


def test_compare_modules_mismatch_propagates():
    meta_mod = ModuleOp([_make_table("scheme_run", [("temp", _real("in"))])])
    fir_mod  = ModuleOp([_make_table("scheme_run", [("temp", _real("inout"))])])
    mm = compare_modules(meta_mod, fir_mod)
    assert len(mm) == 1
    assert mm[0].field == "intent"


def test_mismatch_str_extra_in_meta():
    m = Mismatch("scheme_run", "ghost", "extra_in_meta", "", "")
    assert "ghost" in str(m)
    assert "missing from Fortran" in str(m)


def test_mismatch_str_extra_in_fir():
    m = Mismatch("scheme_run", "mystery", "extra_in_fir", "", "")
    assert "mystery" in str(m)
    assert "missing from .meta" in str(m)


def test_mismatch_str_field():
    m = Mismatch("scheme_run", "temp", "type", "integer", "real")
    s = str(m)
    assert "type" in s
    assert "integer" in s
    assert "real" in s


# ── collect_standard_names ────────────────────────────────────────────────────

def test_collect_standard_names_basic():
    arg1 = ArgumentOp("foo", "integer", {
        "type": "integer", "intent": "in",
        "standard_name": "horizontal_loop_extent", "dimensions": "()",
    })
    arg2 = ArgumentOp("bar", "real", {
        "type": "real", "intent": "in",
        "standard_name": "air_temperature",
        "dimensions": "(horizontal_loop_extent)",
    })
    table = ArgumentTableOp("scheme_run", "scheme", [arg1, arg2])
    mod = ModuleOp([table])
    names = collect_standard_names(mod)
    assert "horizontal_loop_extent" in names
    assert "air_temperature" in names


def test_collect_standard_names_skips_unnamed():
    arg = ArgumentOp("foo", "integer", {"type": "integer", "intent": "in", "dimensions": "()"})
    table = ArgumentTableOp("scheme_run", "scheme", [arg])
    mod = ModuleOp([table])
    assert collect_standard_names(mod) == set()


# ── check_dimension_names ─────────────────────────────────────────────────────

def _scheme_arg(name, std_name, dims):
    return ArgumentOp(name, "real", {
        "type": "real", "intent": "in",
        "standard_name": std_name,
        "dimensions": dims,
    })


def _scheme_mod(arg_ops):
    from xdsl_ccpp.dialects.ccpp import TablePropertiesOp
    table = ArgumentTableOp("scheme_run", "scheme", arg_ops)
    props = TablePropertiesOp("scheme_mod", "scheme", [table])
    return ModuleOp([props])


def test_check_dim_names_all_known():
    mod = _scheme_mod([_scheme_arg("temp", "air_temperature", "(horizontal_loop_extent)")])
    assert check_dimension_names(mod, {"horizontal_loop_extent"}) == []


def test_check_dim_names_unregistered():
    mod = _scheme_mod([_scheme_arg("temp", "air_temperature", "(unknown_dim)")])
    mm = check_dimension_names(mod, {"horizontal_loop_extent"})
    assert len(mm) == 1
    assert mm[0].field == "unregistered_dim"
    assert mm[0].meta_value == "unknown_dim"


def test_check_dim_names_skips_numeric():
    mod = _scheme_mod([_scheme_arg("temp", "air_temperature", "(horizontal_dimension,6)")])
    assert check_dimension_names(mod, {"horizontal_dimension"}) == []


def test_check_dim_names_multidim():
    mod = _scheme_mod([
        _scheme_arg("temp", "air_temperature", "(horizontal_dimension,vertical_layer_dimension)")
    ])
    known = {"horizontal_dimension", "vertical_layer_dimension"}
    assert check_dimension_names(mod, known) == []


def test_check_dim_names_scalar_skipped():
    mod = _scheme_mod([_scheme_arg("errflg", "ccpp_error_code", "()")])
    assert check_dimension_names(mod, set()) == []


def test_mismatch_str_unregistered_dim():
    m = Mismatch("scheme_run", "temp", "unregistered_dim", "mystery_dim", "")
    s = str(m)
    assert "mystery_dim" in s
    assert "not registered" in s
