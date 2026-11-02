"""Unit tests for the OpenACC residency classifier (`_classify_acc_residency`
in `fparser2_to_meta.py`, acc-derive-memory-space) and its use in
`_extract_subroutines`.

An entry point's own `!$acc` directives classify each dummy argument as
"device" (present/deviceptr, update, host_data use_device, arrays inside a
default(present) construct) or "either" (copy-family clauses, arrays inside
a compute construct with no clause for them). Derived-type arguments and
components are never classified: the scheme moves its own derived-type
data. These tests cover the directive grammar (continuations, the
`!!$acc` disabled-directive trap, `default(present)` not being a
`present(...)` clause, subscripts, modifiers), construct bodies, and
integration into `_extract_subroutines`, including real-file regressions.
"""

import pytest

pytest.importorskip("fparser", reason="fparser not installed")

from xdsl_ccpp.transforms.fparser2_to_meta import (
    ACC_DEVICE,
    ACC_EITHER,
    _extract_subroutines,
)


def _classify(body: str, decls: str = "", args: str = "temp, qv, ps, n, gas",
              language: str = "acc"):
    """Classify the dummies of m_run(<args>) whose body is *body* by its
    *language* directives: a dict name -> (category, how), plus the
    derived-type names."""
    src = f"""
module m
contains
  subroutine m_run({args})
    integer, intent(in) :: n
    real, intent(inout) :: temp(:,:), qv(:,:)
    real, intent(in) :: ps(:)
    type(gas_t), intent(inout) :: gas
{decls}
    integer :: i, k
    real :: work(10)
{body}
  end subroutine
end module
"""
    residency = {}
    _extract_subroutines(src, "test.F90", None, residency, language)
    r = residency["m_run"]
    return {k: (v.category, v.how) for k, v in r.args.items()}, set(r.derived_types)


# ── grammar ──────────────────────────────────────────────────────────────────

def test_present_and_deviceptr_are_device():
    got, _ = _classify("    !$acc data present(temp) deviceptr(qv)\n    !$acc end data")
    assert got == {"temp": (ACC_DEVICE, "present"), "qv": (ACC_DEVICE, "deviceptr")}


def test_copy_family_is_either():
    for keyword in ("copy", "copyin", "copyout", "create", "pcopyin", "present_or_copy"):
        got, _ = _classify(f"    !$acc data {keyword}(temp)\n    !$acc end data")
        assert got == {"temp": (ACC_EITHER, keyword)}, keyword


def test_device_outranks_either():
    got, _ = _classify(
        "    !$acc data copyin(temp)\n    !$acc end data\n"
        "    !$acc data present(temp)\n    !$acc end data"
    )
    assert got == {"temp": (ACC_DEVICE, "present")}


def test_update_and_host_data_are_device():
    got, _ = _classify(
        "    !$acc update self(temp) device(qv)\n"
        "    !$acc host_data use_device(ps)\n    !$acc end host_data"
    )
    assert got == {
        "temp": (ACC_DEVICE, "self"), "qv": (ACC_DEVICE, "device"),
        "ps": (ACC_DEVICE, "use_device"),
    }


def test_subscripts_and_modifiers_stripped():
    got, _ = _classify("    !$acc data copyin(readonly: temp(1:n, :), qv(1, (k)))\n    !$acc end data")
    assert got == {"temp": (ACC_EITHER, "copyin"), "qv": (ACC_EITHER, "copyin")}


def test_continuation_line_joined():
    got, _ = _classify(
        "    !$acc data copyin(qv) &\n    !$acc present(temp)\n    !$acc end data"
    )
    assert got == {"qv": (ACC_EITHER, "copyin"), "temp": (ACC_DEVICE, "present")}


def test_default_present_is_not_a_present_clause():
    # 'present' is default's value; with no compute body, nothing is classified.
    got, _ = _classify("    !$acc data default(present)\n    !$acc end data")
    assert got == {}


def test_disabled_directive_ignored():
    got, _ = _classify("    !!$acc data present(temp)\n    !!$acc end data")
    assert got == {}


def test_omp_not_read_as_acc():
    got, _ = _classify("    !$omp target data map(to: temp)\n    !$omp end target data")
    assert got == {}


def test_acc_not_read_as_omp():
    got, _ = _classify("    !$acc data present(temp)\n    !$acc end data", language="omp")
    assert got == {}


# ── OpenMP target offload (omp-derive-memory-space) ──────────────────────────

def _omp(body: str):
    return _classify(body, language="omp")


def test_omp_map_types_are_either():
    got, _ = _omp(
        "    !$omp target data map(to: temp) map(from: qv(1:n, :)) map(ps)\n"
        "    !$omp end target data"
    )
    assert got == {
        "temp": (ACC_EITHER, "map(to)"), "qv": (ACC_EITHER, "map(from)"),
        "ps": (ACC_EITHER, "map(tofrom)"),
    }


def test_omp_present_modifier_is_device():
    got, _ = _omp("    !$omp target data map(present, alloc: temp, qv)\n    !$omp end target data")
    assert got == {"temp": (ACC_DEVICE, "map(present)"), "qv": (ACC_DEVICE, "map(present)")}


def test_omp_release_and_delete_ignored():
    got, _ = _omp("    !$omp target exit data map(release: temp) map(delete: qv)")
    assert got == {}


def test_omp_update_and_device_pointer_clauses_are_device():
    got, _ = _omp(
        "    !$omp target update to(temp) from(present: qv)\n"
        "    !$omp target data use_device_addr(ps)\n    !$omp end target data"
    )
    assert got == {
        "temp": (ACC_DEVICE, "update to"), "qv": (ACC_DEVICE, "update from"),
        "ps": (ACC_DEVICE, "use_device_addr"),
    }


def test_omp_target_loop_body_arrays_are_either():
    # examples/kessler_omp's shape: no map, implicitly tofrom.
    got, _ = _omp(
        "    !$omp target teams distribute parallel do collapse(2)\n"
        "    do k = 1, n\n      do i = 1, n\n"
        "        temp(i,k) = qv(i,k) * ps(i)\n"
        "      end do\n    end do\n"
    )
    assert got == {
        "temp": (ACC_EITHER, "implicit"), "qv": (ACC_EITHER, "implicit"),
        "ps": (ACC_EITHER, "implicit"),
    }


def test_omp_defaultmap_present_body_arrays_are_device():
    got, _ = _omp(
        "    !$omp target teams loop defaultmap(present)\n"
        "    do i = 1, n\n      temp(i,1) = qv(i,1)\n    end do\n"
    )
    assert got == {
        "temp": (ACC_DEVICE, "defaultmap(present)"), "qv": (ACC_DEVICE, "defaultmap(present)"),
    }


def test_omp_target_region_body_ends_at_end_target():
    got, _ = _omp(
        "    !$omp target\n    !$omp teams distribute parallel do\n"
        "    do i = 1, n\n      qv(i,1) = 0.\n    end do\n    !$omp end target\n"
        "    temp(1,1) = ps(1)\n"
    )
    assert got == {"qv": (ACC_EITHER, "implicit")}


def test_omp_host_parallel_do_not_classified():
    got, _ = _omp(
        "    !$omp parallel do\n    do i = 1, n\n      qv(i,1) = 0.\n    end do\n"
    )
    assert got == {}


def test_omp_derived_types_never_classified():
    got, derived = _omp(
        "    !$omp target data map(to: gas, gas%conc) map(present, alloc: temp)\n"
        "    !$omp end target data\n"
    )
    assert got == {"temp": (ACC_DEVICE, "map(present)")}
    assert derived == {"gas"}


def test_real_kessler_omp_file():
    # examples/kessler_omp: every argument its .meta declares device is an
    # implicitly mapped array of a target loop ("either").
    residency = {}
    with open("examples/kessler_omp/scheme/kessler_update.F90") as f:
        _extract_subroutines(f.read(), "kessler_update.F90", None, residency, "omp")
    got = {p: {n: u.category for n, u in r.args.items()} for p, r in residency.items() if r.args}
    assert got == {
        "kessler_update_timestep_init": dict.fromkeys(("temp", "temp_prev", "ttend_t"), ACC_EITHER),
        "kessler_update_run": dict.fromkeys(("theta", "exner", "temp_prev", "ttend_t"), ACC_EITHER),
        "kessler_update_timestep_final": dict.fromkeys(
            ("cpair", "temp", "zm", "phis", "st_energy"), ACC_EITHER),
    }


def test_locals_and_private_ignored():
    got, _ = _classify(
        "    !$acc parallel loop present(work) private(i) reduction(+:k)\n"
        "    do i = 1, n\n      k = k + i\n    end do"
    )
    assert got == {}


def test_unterminated_clause_raises():
    with pytest.raises(ValueError, match=r"test.F90:\d+: .* has no closing"):
        _classify("    !$acc data present(temp\n    !$acc end data")


# ── compute construct bodies ─────────────────────────────────────────────────

def test_loop_body_arrays_are_either_without_clause():
    # kessler_update_timestep_init's shape: a bare parallel loop.
    got, _ = _classify(
        "    !$acc parallel loop collapse(2)\n"
        "    do k = 1, n\n      do i = 1, n\n"
        "        temp(i,k) = qv(i,k) * ps(i)\n"
        "      end do\n    end do\n"
    )
    assert got == {
        "temp": (ACC_EITHER, "implicit"), "qv": (ACC_EITHER, "implicit"),
        "ps": (ACC_EITHER, "implicit"),
    }


def test_default_present_body_arrays_are_device():
    # kessler_run's relhum: assigned in the loop, named in no clause.
    got, _ = _classify(
        "    !$acc parallel loop present(qv) default(present)\n"
        "    do i = 1, n\n      temp(i,1) = qv(i,1)\n    end do\n"
    )
    assert got == {
        "qv": (ACC_DEVICE, "present"), "temp": (ACC_DEVICE, "default(present)"),
    }


def test_only_the_loop_after_the_directive_is_its_body():
    got, _ = _classify(
        "    !$acc parallel loop\n    do i = 1, n\n      qv(i,1) = 0.\n    end do\n"
        "    do i = 1, n\n      temp(i,1) = ps(i)\n    end do\n"
    )
    assert got == {"qv": (ACC_EITHER, "implicit")}


def test_parallel_region_body_ends_at_end_directive():
    got, _ = _classify(
        "    !$acc parallel default(present)\n    !$acc loop\n"
        "    do i = 1, n\n      qv(i,1) = 0.\n    end do\n    !$acc end parallel\n"
        "    temp(1,1) = ps(1)\n"
    )
    assert got == {"qv": (ACC_DEVICE, "default(present)")}


def test_scalars_in_body_not_classified():
    got, _ = _classify(
        "    !$acc parallel loop\n    do i = 1, n\n      qv(i,1) = 0.\n    end do\n"
    )
    assert "n" not in got


def test_comments_and_strings_in_body_ignored():
    got, _ = _classify(
        "    !$acc parallel loop\n    do i = 1, n\n"
        "      qv(i,1) = 0. ! temp(i,1)\n    end do\n"
    )
    assert got == {"qv": (ACC_EITHER, "implicit")}


# ── derived types ─────────────────────────────────────────────────────────────

def test_derived_types_never_classified():
    got, derived = _classify(
        "    !$acc data copyin(gas, gas%conc, gas%conc%vmr) present(temp)\n"
        "    !$acc end data\n"
        "    !$acc parallel loop\n    do i = 1, n\n      qv(i,1) = gas%conc(i)\n    end do\n"
    )
    assert got == {"temp": (ACC_DEVICE, "present"), "qv": (ACC_EITHER, "implicit")}
    assert derived == {"gas"}


def test_component_name_matching_a_dummy_not_classified():
    # gas%temp names gas's component, not the dummy temp.
    got, derived = _classify(
        "    !$acc parallel loop\n    do i = 1, n\n      qv(i,1) = gas%temp(i)\n    end do\n"
    )
    assert got == {"qv": (ACC_EITHER, "implicit")}
    assert derived == {"gas"}


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
    # A bare `!$acc parallel loop` (no clause): its arrays are "either",
    # which generated .meta still maps to device (stage 1).
    assert flagged.get("kessler_update_timestep_init") == {"temp", "temp_prev", "ttend_t"}


def test_real_kessler_file_default_present():
    # relhum is named in no clause of kessler_run's default(present) loop.
    residency = {}
    with open("examples/kessler/scheme/kessler.F90") as f:
        _extract_subroutines(f.read(), "kessler.F90", None, residency)
    r = residency["kessler_run"]
    assert {n for n, u in r.args.items() if u.category == ACC_DEVICE} == {
        "cpair", "rair", "rho", "z", "pk", "theta", "qv", "qc", "qr", "precl", "relhum"
    }
    assert r.args["relhum"].how == "default(present)"
