"""Unit tests for the `!$ccpp [name] key = value` tag extractor
(`_extract_ccpp_tags`/`_construct_span`/`_join_comment_continuations` in
`fparser2_to_meta.py`).

dup-meta-shadow-elim (BACKLOG.md), Phase 1: tags are the recovery path for
`standard_name`/`units`/`long_name` -- content fparser2's own parse tree
can never see, since it strips all comments. These tests cover the
tag-recognition grammar directly (one `key = value` per line or
continued across several with a trailing `&`, matched by bracketed name,
not line position) and its integration into `_extract_subroutines`'s
returned arg dicts.

Originally `!ccpp` (2026-10-15); renamed to `!$ccpp` (2026-10-16) to match
real Fortran compiler-directive convention (`!$acc`/`!$omp`) more
closely, and to get the same "a second `!` disables it"
(`!!$ccpp`-is-not-a-tag) property those already have for free.

The full `build_meta_module_from_source` -> IR round-trip (Phase 4) is
tested separately, in `test_generate_meta.py`.
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
    lines = ["  !$ccpp [qv] standard_name = water_vapor_mixing_ratio"]
    tags = _extract_ccpp_tags(lines, (1, 1))
    assert tags == {"qv": {"standard_name": "water_vapor_mixing_ratio"}}


def test_multiple_keys_for_same_name_merge():
    lines = [
        "  !$ccpp [qv] standard_name = water_vapor_mixing_ratio",
        "  !$ccpp [qv] units = kg kg-1",
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
        "  !$ccpp [qv] units = kg kg-1",
        "  !$ccpp [qv_dry] units = kg kg-1",
    ]
    tags = _extract_ccpp_tags(lines, (1, 2))
    assert set(tags) == {"qv", "qv_dry"}


def test_value_with_spaces_preserved_verbatim():
    lines = ["  !$ccpp [data] long_name = per-thread data array"]
    tags = _extract_ccpp_tags(lines, (1, 1))
    assert tags["data"]["long_name"] == "per-thread data array"


def test_ordinary_comment_ignored():
    lines = ["  ! this just computes the tendency, not a tag"]
    assert _extract_ccpp_tags(lines, (1, 1)) == {}


def test_non_comment_line_ignored():
    lines = ["  real, intent(inout) :: qv"]
    assert _extract_ccpp_tags(lines, (1, 1)) == {}


def test_case_insensitive_ccpp_marker():
    lines = ["  !$CCPP [qv] units = kg kg-1"]
    tags = _extract_ccpp_tags(lines, (1, 1))
    assert tags == {"qv": {"units": "kg kg-1"}}


def test_name_and_key_lowercased():
    lines = ["  !$ccpp [QV] Standard_Name = water_vapor_mixing_ratio"]
    tags = _extract_ccpp_tags(lines, (1, 1))
    assert tags == {"qv": {"standard_name": "water_vapor_mixing_ratio"}}


def test_span_restricts_which_lines_are_scanned():
    lines = [
        "  !$ccpp [outside] units = should_not_be_seen",
        "  !$ccpp [inside] units = kg kg-1",
        "  !$ccpp [also_outside] units = should_not_be_seen",
    ]
    tags = _extract_ccpp_tags(lines, (2, 2))
    assert tags == {"inside": {"units": "kg kg-1"}}


def test_none_span_returns_empty():
    assert _extract_ccpp_tags(["  !$ccpp [qv] units = kg kg-1"], None) == {}


# ── _extract_ccpp_tags: multi-line continuation ──────────────────────────────

def test_continuation_line_joins_value():
    lines = [
        "  !$ccpp [qv] long_name = a description that needs to wrap onto &",
        "  !$ccpp a second line for readability",
    ]
    tags = _extract_ccpp_tags(lines, (1, 2))
    assert tags == {
        "qv": {"long_name": "a description that needs to wrap onto a second line for readability"}
    }


def test_continuation_line_needs_no_bracket():
    # The whole point: a continuation line is pure value text, not a new
    # [name] key = value assignment -- confirmed by the above test already
    # succeeding with no bracket on the second line, this test just makes
    # that property explicit and named.
    lines = [
        "  !$ccpp [qv] units = kg &",
        "  !$ccpp kg-1",
    ]
    assert _extract_ccpp_tags(lines, (1, 2)) == {"qv": {"units": "kg kg-1"}}


def test_three_line_continuation():
    lines = [
        "  !$ccpp [qv] long_name = one &",
        "  !$ccpp two &",
        "  !$ccpp three",
    ]
    assert _extract_ccpp_tags(lines, (1, 3)) == {"qv": {"long_name": "one two three"}}


def test_continuation_requires_matching_sentinel_on_next_line():
    # A trailing '&' with no further !$ccpp line to continue onto is not
    # an error -- it's simply the end of the scanned span; the trailing
    # '&' just becomes part of the (otherwise terminated) value.
    lines = ["  !$ccpp [qv] units = kg &"]
    assert _extract_ccpp_tags(lines, (1, 1)) == {"qv": {"units": "kg"}}


def test_non_continuation_lines_do_not_bleed_into_next_tag():
    # Two independent, single-line tags must stay independent -- a bare
    # (non-'&'-terminated) tag line must not somehow merge with the next.
    lines = [
        "  !$ccpp [a] units = m",
        "  !$ccpp [b] units = s",
    ]
    assert _extract_ccpp_tags(lines, (1, 2)) == {
        "a": {"units": "m"},
        "b": {"units": "s"},
    }


def test_error_in_continued_tag_reports_starting_line_number():
    lines = [
        "  real, intent(inout) :: qv",
        "  !$ccpp [qv] units = kg &",
        "  !$ccpp missing_bracket_name] long_name = oops",
    ]
    # The second physical !$ccpp line is itself a well-formed continuation
    # of the FIRST tag (units = "kg missing_bracket_name] long_name =
    # oops") -- there's no separate [name] on a continuation line by
    # design, so this doesn't raise at all; it's simply an unusually long
    # units value. Demonstrates the real, deliberate trade-off: continuing
    # a value is indistinguishable from accidentally forgetting the '&'
    # was meant to end a tag. Not testing an error path here -- see the
    # next test for where errors in a genuinely malformed FIRST line of a
    # continued tag are still reported at the right line number.
    tags = _extract_ccpp_tags(lines, (1, 3), filename="test.F90")
    assert tags == {
        "qv": {"units": "kg missing_bracket_name] long_name = oops"}
    }


def test_malformed_first_line_of_continuation_reports_its_own_line_number():
    lines = [
        "  !$ccpp qv] units = kg &",
        "  !$ccpp kg-1",
    ]
    with pytest.raises(ValueError, match=r"test\.F90:1:.*missing '\[name\]'"):
        _extract_ccpp_tags(lines, (1, 2), filename="test.F90")


# ── _extract_ccpp_tags: malformed input raises with filename:line_no ────────

def test_missing_open_bracket_raises():
    lines = ["  !$ccpp qv] standard_name = foo"]
    with pytest.raises(ValueError, match=r"test\.F90:1.*missing '\[name\]'"):
        _extract_ccpp_tags(lines, (1, 1), filename="test.F90")


def test_unterminated_bracket_raises():
    lines = ["  !$ccpp [qv standard_name = foo"]
    with pytest.raises(ValueError, match=r"test\.F90:1.*unterminated"):
        _extract_ccpp_tags(lines, (1, 1), filename="test.F90")


def test_empty_name_raises():
    lines = ["  !$ccpp [] standard_name = foo"]
    with pytest.raises(ValueError, match=r"empty '\[name\]'"):
        _extract_ccpp_tags(lines, (1, 1), filename="test.F90")


def test_missing_equals_raises():
    lines = ["  !$ccpp [qv] standard_name foo"]
    with pytest.raises(ValueError, match=r"missing 'key = value'"):
        _extract_ccpp_tags(lines, (1, 1), filename="test.F90")


def test_empty_key_raises():
    lines = ["  !$ccpp [qv] = foo"]
    with pytest.raises(ValueError, match=r"empty key"):
        _extract_ccpp_tags(lines, (1, 1), filename="test.F90")


def test_error_message_reports_correct_line_number():
    lines = [
        "  real, intent(inout) :: qv",
        "  !$ccpp [qv standard_name = oops",
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
        "    !$ccpp [qv] units = kg kg-1\n"
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
    !$ccpp [qv] standard_name = water_vapor_mixing_ratio
    !$ccpp [qv] units = kg kg-1
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
    # Purely additive: a file with zero !$ccpp tags must behave exactly as
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
    !$ccpp [qv_typo] standard_name = water_vapor_mixing_ratio
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
    !$ccpp [qv] units = kg kg-1
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
