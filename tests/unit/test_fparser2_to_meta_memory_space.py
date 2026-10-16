"""Unit tests for the `!$acc`/`!$omp` device-residency scan
(`_extract_device_resident_vars` in `fparser2_to_meta.py`).

dup-meta-shadow-elim (BACKLOG.md), Phase 2: real, active GPU directives
(`present`/`deviceptr`/`copyin`/`copyout`/`copy`) already name exactly
which dummy arguments need `memory_space = device` -- confirmed against
real usage in this repo's own `examples/kessler`, `examples/advection`,
`examples/advection_flat_host`. These tests cover the directive-scanning
grammar directly (continuation-line joining, the `!!$acc` disabled-
directive trap, the `default(present)` false-match trap) and integration
into `_extract_subroutines`'s returned arg dicts, including a real-file
regression test locking in today's verified-correct result.
"""

import pytest

pytest.importorskip("fparser", reason="fparser not installed")

from xdsl_ccpp.transforms.fparser2_to_meta import (
    _extract_device_resident_vars,
    _extract_subroutines,
)


# ── _extract_device_resident_vars: grammar ──────────────────────────────────

def test_single_present_clause():
    lines = ["    !$acc parallel loop present(temp)"]
    assert _extract_device_resident_vars(lines, (1, 1)) == {"temp"}


def test_multiple_vars_in_one_clause():
    lines = ["    !$acc parallel loop present(temp, temp_prev, ttend_t)"]
    assert _extract_device_resident_vars(lines, (1, 1)) == {
        "temp", "temp_prev", "ttend_t"
    }


def test_each_residency_keyword_recognized():
    for keyword in ("present", "deviceptr", "copyin", "copyout", "copy"):
        lines = [f"    !$acc parallel loop {keyword}(qv)"]
        assert _extract_device_resident_vars(lines, (1, 1)) == {"qv"}, keyword


def test_non_residency_clauses_ignored():
    # private/reduction/default/create are about a variable's own lifecycle
    # or GPU control flow, not dummy-argument memory_space -- deliberately
    # out of scope.
    lines = [
        "    !$acc parallel loop gang vector private(dtmin) "
        "reduction(min:dtmin) default(present)"
    ]
    assert _extract_device_resident_vars(lines, (1, 1)) == set()


def test_default_present_not_mistaken_for_present_clause():
    # 'present' here is default's VALUE, not a clause keyword -- it's
    # followed by ')', not '('.
    lines = ["    !$acc parallel loop gang vector default(present)"]
    assert _extract_device_resident_vars(lines, (1, 1)) == set()


def test_continuation_line_joined():
    lines = [
        "    !$acc parallel loop gang vector &",
        "    !$acc present(cpair,rair,pk) default(present)",
    ]
    assert _extract_device_resident_vars(lines, (1, 2)) == {"cpair", "rair", "pk"}


def test_omp_sentinel_also_recognized():
    lines = ["    !$omp target present(qv)"]
    assert _extract_device_resident_vars(lines, (1, 1)) == {"qv"}


def test_disabled_directive_not_recognized():
    # Real compiler sentinel is exactly '!$acc' -- a second '!' means this
    # is a human comment about a directive, not a real one. Confirmed real
    # case: examples/kessler/scheme/kessler_update.F90 has exactly this
    # shape (a commented-out fuller directive next to an active, shorter
    # one with no present() at all).
    lines = [
        "    !!$acc parallel loop collapse(2) present(temp, temp_prev, ttend_t)",
        "    !$acc parallel loop collapse(2)",
    ]
    assert _extract_device_resident_vars(lines, (1, 2)) == set()


def test_span_restricts_which_lines_are_scanned():
    lines = [
        "    !$acc parallel loop present(outside)",
        "    !$acc parallel loop present(inside)",
        "    !$acc parallel loop present(also_outside)",
    ]
    assert _extract_device_resident_vars(lines, (2, 2)) == {"inside"}


def test_none_span_returns_empty_set():
    lines = ["    !$acc parallel loop present(qv)"]
    assert _extract_device_resident_vars(lines, None) == set()


def test_unterminated_clause_raises():
    lines = ["    !$acc parallel loop present(temp"]
    with pytest.raises(ValueError, match=r"no closing '\)'"):
        _extract_device_resident_vars(lines, (1, 1), filename="test.F90")


# ── integration: _extract_subroutines merges memory_space ──────────────────

def test_memory_space_merged_for_matching_argument():
    src = """
module m
contains
  subroutine m_run(temp, errflg)
    real, intent(inout) :: temp
    integer, intent(out) :: errflg
    !$acc parallel loop present(temp)
    errflg = 0
  end subroutine
end module
"""
    results = _extract_subroutines(src, filename="test.F90")
    by_name = {a["name"]: a for a in results[0][2]}
    assert by_name["temp"]["memory_space"] == "device"
    assert "memory_space" not in by_name["errflg"]


def test_local_scratch_variable_in_clause_does_not_error():
    # present(local_work_array) names a plain local, not a dummy argument
    # -- unlike an unmatched !$ccpp tag, this must not raise.
    src = """
module m
contains
  subroutine m_run(temp, errflg)
    real, intent(inout) :: temp
    integer, intent(out) :: errflg
    real :: local_work_array(10)
    !$acc parallel loop present(temp, local_work_array)
    errflg = 0
  end subroutine
end module
"""
    results = _extract_subroutines(src, filename="test.F90")
    by_name = {a["name"]: a for a in results[0][2]}
    assert by_name["temp"]["memory_space"] == "device"
    assert "local_work_array" not in by_name


def test_explicit_tag_takes_precedence_over_derived_value():
    # An explicit !$ccpp memory_space tag is a human override and must win
    # over whatever the directive scan would otherwise derive.
    src = """
module m
contains
  subroutine m_run(temp, errflg)
    !$ccpp [temp] memory_space = unified
    real, intent(inout) :: temp
    integer, intent(out) :: errflg
    !$acc parallel loop present(temp)
    errflg = 0
  end subroutine
end module
"""
    results = _extract_subroutines(src, filename="test.F90")
    by_name = {a["name"]: a for a in results[0][2]}
    assert by_name["temp"]["memory_space"] == "unified"


def test_untagged_undirected_source_entirely_unaffected():
    src = """
module m
contains
  subroutine m_run(temp)
    real, intent(inout) :: temp(:)
  end subroutine
end module
"""
    results = _extract_subroutines(src, filename="test.F90")
    assert "memory_space" not in results[0][2][0]


# ── real-file regression test ───────────────────────────────────────────────

def test_real_kessler_update_file():
    with open("examples/kessler/scheme/kessler_update.F90") as f:
        src = f.read()
    results = _extract_subroutines(src, filename="kessler_update.F90")
    flagged = {
        proc: {a["name"] for a in args if a.get("memory_space")}
        for _, proc, args in results
    }
    assert flagged.get("kessler_update_run") == {
        "theta", "exner", "temp_prev", "ttend_t"
    }
    assert flagged.get("kessler_update_timestep_final") == {
        "cpair", "temp", "zm", "phis", "st_energy"
    }
