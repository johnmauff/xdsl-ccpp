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
    ACC_HOST,
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


# ── acc-copy-residency: "either" arrays also used in host code ───────────────

_KERNEL = (
    "    !$acc parallel loop copyin(ps) copy(temp)\n"
    "    do i = 1, n\n"
    "      temp(i, 1) = temp(i, 1) + ps(i)\n"
    "    end do\n"
)


def test_copy_clause_arrays_used_only_in_the_kernel_stay_either():
    got, _ = _classify(_KERNEL)
    assert got == {"ps": (ACC_EITHER, "copyin"), "temp": (ACC_EITHER, "copy")}


def test_host_write_before_the_kernel_makes_it_host():
    # With temp resident, copy(temp) copies nothing: the kernel would not
    # see this host write. The cap must sync around the call instead.
    got, _ = _classify("    temp(1, 1) = 0.0\n" + _KERNEL)
    assert got["temp"] == (ACC_HOST, "host use")
    assert got["ps"] == (ACC_EITHER, "copyin")


def test_host_read_after_the_kernel_makes_it_host():
    got, _ = _classify(_KERNEL + "    qv(1, 1) = temp(1, 1)\n")
    assert got["temp"] == (ACC_HOST, "host use")


def test_inquiry_intrinsics_are_not_host_uses():
    got, _ = _classify(
        "    k = size(temp, 1) + lbound(ps, 1)\n"
        "    if (present(ps)) k = ubound(temp, 2)\n" + _KERNEL
    )
    assert got == {"ps": (ACC_EITHER, "copyin"), "temp": (ACC_EITHER, "copy")}


def test_host_use_inside_a_data_region_is_still_host():
    # A data region is not a compute construct: the code in it runs on the host.
    got, _ = _classify(
        "    !$acc data copy(temp)\n"
        "    temp(1, 1) = 0.0\n"
        "    !$acc parallel loop\n"
        "    do i = 1, n\n"
        "      temp(i, 1) = temp(i, 1) + 1.0\n"
        "    end do\n"
        "    !$acc end data\n"
    )
    assert got["temp"] == (ACC_HOST, "host use")


def test_host_use_does_not_change_device_arguments():
    # present(): the scheme requires the data on the device; its host code
    # is its own business (it must update itself).
    got, _ = _classify(
        "    temp(1, 1) = 0.0\n"
        "    !$acc parallel loop present(temp)\n"
        "    do i = 1, n\n"
        "      temp(i, 1) = 1.0\n"
        "    end do\n"
    )
    assert got["temp"] == (ACC_DEVICE, "present")


# ── classification through callees (apply_callee_residency) ──────────────────
# An entry point with no OpenACC of its own (micro_pumas_ccpp_run) takes its
# arguments' residency from the callee it passes them to (micro_pumas_tend).

_CALLEE = """
  subroutine kern(a, b, c)
    real, intent(inout) :: a(:), b(:), c(:)
    integer :: i
    !$acc data present(a) copy(b, c)
    !$acc parallel loop
    do i = 1, size(a)
      a(i) = b(i) + c(i)
    end do
    !$acc end data
    c(1) = 0.
  end subroutine
"""


def _through_callee(entry_body: str, extra: str = ""):
    from xdsl_ccpp.transforms.fparser2_to_meta import apply_callee_residency

    src = f"""
module m
contains
  subroutine m_run(x, y, z)
    real, intent(inout) :: x(:), y(:), z(:)
{entry_body}
  end subroutine
{_CALLEE}
{extra}
end module
"""
    residency = {}
    _extract_subroutines(src, "test.F90", None, residency, "acc")
    apply_callee_residency(residency)
    r = residency["m_run"]
    return {k: (v.category, v.how) for k, v in r.args.items()}, r


def test_positional_actuals_take_the_callee_category():
    got, r = _through_callee("    call kern(x, y, z)")
    assert got == {
        "x": (ACC_DEVICE, "present in kern"),
        "y": (ACC_EITHER, "copy in kern"),
        "z": (ACC_HOST, "host use in kern"),  # kern uses c in host code
    }
    assert r.via_callees == {"kern"} and not r.has_acc


def test_keyword_actuals_map_by_name():
    got, _ = _through_callee("    call kern(c=x, a=y, b=z)")
    assert got == {
        "x": (ACC_HOST, "host use in kern"),
        "y": (ACC_DEVICE, "present in kern"),
        "z": (ACC_EITHER, "copy in kern"),
    }


def test_host_use_outside_the_call_makes_it_host():
    got, _ = _through_callee("    x(1) = 1.\n    call kern(x, y, z)")
    assert got["x"][0] == ACC_HOST
    assert got["y"] == (ACC_EITHER, "copy in kern")


def test_section_actual_or_callee_without_acc_not_classified():
    extra = """
  subroutine plain(a)
    real, intent(inout) :: a(:)
    a = 0.
  end subroutine
"""
    got, _ = _through_callee("    call kern(x(1:2), y, z)\n    call plain(z)", extra)
    assert "x" not in got  # passed as a section
    assert got["z"][0] == ACC_HOST  # also passed to plain, a callee with no OpenACC
    assert got["y"] == (ACC_EITHER, "copy in kern")


def test_entry_point_with_its_own_acc_ignores_callees():
    got, r = _through_callee("    !$acc data copyin(z)\n    call kern(x, y, z)\n    !$acc end data")
    assert set(got) == {"z"} and r.via_callees == set()


def test_callee_in_a_meta_dependency_file_is_read(tmp_path):
    from xdsl_ccpp.tools.ccpp_dsl import _check_fortran_source

    (tmp_path / "dep.F90").write_text(f"module dep\ncontains\n{_CALLEE}\nend module\n")
    (tmp_path / "s.F90").write_text("""
module s
contains
  subroutine s_run(x, y, errmsg, errflg)
    use dep, only: kern
    real, intent(inout) :: x(:), y(:)
    character(len=*), intent(out) :: errmsg
    integer, intent(out) :: errflg
    errmsg = ''
    errflg = 0
    call kern(x, y, y)
  end subroutine
end module
""")
    arg = "  type = real | kind = kind_phys\n  units = 1\n  intent = inout\n"
    (tmp_path / "s.meta").write_text(f"""[ccpp-table-properties]
  name = s
  type = scheme
  dependencies = dep.F90
[ccpp-arg-table]
  name = s_run
  type = scheme
[ x ]
  standard_name = x_var
  dimensions = (horizontal_dimension)
{arg}[ y ]
  standard_name = y_var
  dimensions = (horizontal_dimension)
{arg}[ errmsg ]
  standard_name = ccpp_error_message
  units = none
  dimensions = ()
  type = character | kind = len=*
  intent = out
[ errflg ]
  standard_name = ccpp_error_code
  units = 1
  dimensions = ()
  type = integer
  intent = out
""")
    _, classification = _check_fortran_source(
        str(tmp_path / "s.meta"), str(tmp_path / "s.F90"), None, 1, "acc"
    )
    assert classification == {"s_run": {"x": ACC_DEVICE, "y": ACC_HOST}}
