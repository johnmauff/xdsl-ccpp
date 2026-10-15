"""Unit tests for the `!ccpp [name] key = value` tag extractor
(`_extract_ccpp_tags`/`_construct_span` in `fparser2_to_meta.py`).

dup-meta-shadow-elim (BACKLOG.md), Phase 1: tags are the recovery path for
`standard_name`/`units`/`long_name` -- content fparser2's own parse tree
can never see, since it strips all comments. These tests cover the
tag-recognition grammar directly (one `key = value` per line, matched by
bracketed name, not line position) and its integration into
`_extract_subroutines`'s returned arg dicts.

Not yet tested here: the full `build_meta_module_from_source` → IR
round-trip. That function still only forwards a fixed set of keys
(`type`/`dimensions`/`intent`/`optional`/`kind`) into `ArgumentOp` --
wiring `standard_name`/`units` through into the IR is Phase 4 work, not
done yet. Testing that here would fail for a reason unrelated to the tag
extractor itself.
"""

import pytest

pytest.importorskip("fparser", reason="fparser not installed")

from xdsl_ccpp.transforms.fparser2_to_meta import (
    _construct_span,
    _extract_ccpp_tags,
    _extract_subroutines,
)


# ── _extract_ccpp_tags: grammar ──────────────────────────────────────────────

def test_single_tag_extracted():
    lines = ["  !ccpp [qv] standard_name = water_vapor_mixing_ratio"]
    tags = _extract_ccpp_tags(lines, (1, 1))
    assert tags == {"qv": {"standard_name": "water_vapor_mixing_ratio"}}


def test_multiple_keys_for_same_name_merge():
    lines = [
        "  !ccpp [qv] standard_name = water_vapor_mixing_ratio",
        "  !ccpp [qv] units = kg kg-1",
    ]
    tags = _extract_ccpp_tags(lines, (1, 2))
    assert tags == {
        "qv": {
            "standard_name": "water_vapor_mixing_ratio",
            "units": "kg kg-1",
        }
    }


def test_multiple_names_kept_separate():
    lines = [
        "  !ccpp [qv] units = kg kg-1",
        "  !ccpp [qv_dry] units = kg kg-1",
    ]
    tags = _extract_ccpp_tags(lines, (1, 2))
    assert set(tags) == {"qv", "qv_dry"}


def test_value_with_spaces_preserved_verbatim():
    lines = ["  !ccpp [data] long_name = per-thread data array"]
    tags = _extract_ccpp_tags(lines, (1, 1))
    assert tags["data"]["long_name"] == "per-thread data array"


def test_ordinary_comment_ignored():
    lines = ["  ! this just computes the tendency, not a tag"]
    assert _extract_ccpp_tags(lines, (1, 1)) == {}


def test_non_comment_line_ignored():
    lines = ["  real, intent(inout) :: qv"]
    assert _extract_ccpp_tags(lines, (1, 1)) == {}


def test_case_insensitive_ccpp_marker():
    lines = ["  !CCPP [qv] units = kg kg-1"]
    tags = _extract_ccpp_tags(lines, (1, 1))
    assert tags == {"qv": {"units": "kg kg-1"}}


def test_name_and_key_lowercased():
    lines = ["  !ccpp [QV] Standard_Name = water_vapor_mixing_ratio"]
    tags = _extract_ccpp_tags(lines, (1, 1))
    assert tags == {"qv": {"standard_name": "water_vapor_mixing_ratio"}}


def test_span_restricts_which_lines_are_scanned():
    lines = [
        "  !ccpp [outside] units = should_not_be_seen",
        "  !ccpp [inside] units = kg kg-1",
        "  !ccpp [also_outside] units = should_not_be_seen",
    ]
    tags = _extract_ccpp_tags(lines, (2, 2))
    assert tags == {"inside": {"units": "kg kg-1"}}


def test_none_span_returns_empty():
    assert _extract_ccpp_tags(["  !ccpp [qv] units = kg kg-1"], None) == {}


# ── _extract_ccpp_tags: malformed input raises with filename:line_no ────────

def test_missing_open_bracket_raises():
    lines = ["  !ccpp qv] standard_name = foo"]
    with pytest.raises(ValueError, match=r"test\.F90:1.*missing '\[name\]'"):
        _extract_ccpp_tags(lines, (1, 1), filename="test.F90")


def test_unterminated_bracket_raises():
    lines = ["  !ccpp [qv standard_name = foo"]
    with pytest.raises(ValueError, match=r"test\.F90:1.*unterminated"):
        _extract_ccpp_tags(lines, (1, 1), filename="test.F90")


def test_empty_name_raises():
    lines = ["  !ccpp [] standard_name = foo"]
    with pytest.raises(ValueError, match=r"empty '\[name\]'"):
        _extract_ccpp_tags(lines, (1, 1), filename="test.F90")


def test_missing_equals_raises():
    lines = ["  !ccpp [qv] standard_name foo"]
    with pytest.raises(ValueError, match=r"missing 'key = value'"):
        _extract_ccpp_tags(lines, (1, 1), filename="test.F90")


def test_empty_key_raises():
    lines = ["  !ccpp [qv] = foo"]
    with pytest.raises(ValueError, match=r"empty key"):
        _extract_ccpp_tags(lines, (1, 1), filename="test.F90")


def test_error_message_reports_correct_line_number():
    lines = [
        "  real, intent(inout) :: qv",
        "  !ccpp [qv standard_name = oops",
    ]
    with pytest.raises(ValueError, match=r"test\.F90:2:"):
        _extract_ccpp_tags(lines, (1, 2), filename="test.F90")


# ── _construct_span ──────────────────────────────────────────────────────────

def test_construct_span_covers_whole_subroutine():
    import fparser.two.Fortran2003 as f03
    from fparser.two.parser import ParserFactory
    from fparser.two.utils import walk
    from fparser.common.readfortran import FortranStringReader

    ParserFactory().create(std="f2003")
    src = (
        "module m\n"
        "contains\n"
        "  subroutine m_run(qv)\n"
        "    !ccpp [qv] units = kg kg-1\n"
        "    real, intent(inout) :: qv\n"
        "  end subroutine m_run\n"
        "end module m\n"
    )
    tree = f03.Program(FortranStringReader(src))
    sub = next(iter(walk(tree, f03.Subroutine_Subprogram)))
    assert _construct_span(sub) == (3, 6)


# ── integration: _extract_subroutines merges tags into arg dicts ───────────

def test_tags_merge_into_matching_argument():
    src = """
module m
contains
  subroutine m_run(qv, errflg)
    !ccpp [qv] standard_name = water_vapor_mixing_ratio
    !ccpp [qv] units = kg kg-1
    real, intent(inout) :: qv
    integer, intent(out) :: errflg
  end subroutine
end module
"""
    results = _extract_subroutines(src, filename="test.F90")
    _, _, args = results[0]
    by_name = {a["name"]: a for a in args}
    assert by_name["qv"]["standard_name"] == "water_vapor_mixing_ratio"
    assert by_name["qv"]["units"] == "kg kg-1"
    # Untagged argument is unaffected -- no standard_name/units key at all,
    # not an empty one.
    assert "standard_name" not in by_name["errflg"]
    assert "units" not in by_name["errflg"]


def test_untagged_source_entirely_unaffected():
    # Purely additive: a file with zero !ccpp tags must behave exactly as
    # before this feature existed -- the real-world case for every example
    # in examples/ today, since none have been migrated to tags yet.
    src = """
module m
contains
  subroutine m_run(temp)
    real, intent(inout) :: temp(:)
  end subroutine
end module
"""
    results = _extract_subroutines(src, filename="test.F90")
    _, _, args = results[0]
    assert args == [
        {"name": "temp", "type": "real", "rank": 1, "intent": "inout",
         "optional": False, "kind": None}
    ]


def test_tag_naming_unknown_argument_raises():
    src = """
module m
contains
  subroutine m_run(qv, errflg)
    !ccpp [qv_typo] standard_name = water_vapor_mixing_ratio
    real, intent(inout) :: qv
    integer, intent(out) :: errflg
  end subroutine
end module
"""
    with pytest.raises(ValueError, match=r"qv_typo.*not one of its own dummy arguments"):
        _extract_subroutines(src, filename="test.F90")


def test_tags_scoped_per_subroutine_not_shared():
    # Two subroutines in the same module each declare their own 'qv' with
    # different tag content -- a tag from one must never leak into the
    # other just because the local name is the same.
    src = """
module m
contains
  subroutine a_run(qv, errflg)
    !ccpp [qv] units = kg kg-1
    real, intent(inout) :: qv
    integer, intent(out) :: errflg
  end subroutine
  subroutine b_run(qv, errflg)
    real, intent(inout) :: qv
    integer, intent(out) :: errflg
  end subroutine
end module
"""
    results = _extract_subroutines(src, filename="test.F90")
    by_proc = {proc_name: {a["name"]: a for a in args} for _, proc_name, args in results}
    assert by_proc["a_run"]["qv"]["units"] == "kg kg-1"
    assert "units" not in by_proc["b_run"]["qv"]
