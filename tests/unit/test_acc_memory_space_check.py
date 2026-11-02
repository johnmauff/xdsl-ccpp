"""acc-derive-memory-space stage 1: the `.meta` memory_space vs OpenACC
comparison (`validate_source.compare_memory_space`, run by ccpp_dsl's
Fortran-vs-.meta check) and the input error for `memory_space = device` on
a scheme's derived-type argument (`ccpp_xml.build_meta_ir`)."""

import pytest

pytest.importorskip("fparser", reason="fparser not installed")

from xdsl.dialects import builtin

from xdsl_ccpp.dialects.ccpp import ArgumentOp, ArgumentTableOp, TablePropertiesOp
from xdsl_ccpp.frontend.ccpp_xml import ccppXML, parse_meta_file
from xdsl_ccpp.tools.ccpp_dsl import _validate_fortran_source
from xdsl_ccpp.transforms.fparser2_to_meta import build_meta_module_from_source
from xdsl_ccpp.transforms.validate_source import compare_memory_space
from xdsl_ccpp.util.errors import CcppInputError

_SOURCE = """
module m
contains
  subroutine m_run(n, a, b, c, d, gas)
    integer, intent(in) :: n
    real, intent(inout) :: a(:), b(:), c(:), d(:)
    type(gas_t), intent(inout) :: gas
    integer :: i
    !$acc data present(a) copyin(c, gas%vmr)
    !$acc parallel loop
    do i = 1, n
      a(i) = c(i)
    end do
    !$acc end data
  end subroutine
  subroutine m_dispatch(n, a)
    integer, intent(in) :: n
    real, intent(inout) :: a(:)
    call m_kernel(n, a)
  end subroutine
  subroutine m_kernel(n, a)
    integer, intent(in) :: n
    real, intent(inout) :: a(:)
    !$acc parallel loop present(a)
    do i = 1, n
      a(i) = 0.
    end do
  end subroutine
  subroutine m_host(n, a)
    integer, intent(in) :: n
    real, intent(inout) :: a(:)
    a = 0.
  end subroutine
end module
"""


def _meta_module(tables: dict[str, dict[str, str | None]]) -> builtin.ModuleOp:
    """Scheme arg tables: table -> {arg: memory_space or None}."""
    arg_tables = []
    for table, args in tables.items():
        ops = []
        for name, space in args.items():
            attrs = {"type": "real", "dimensions": "(dim1)"}
            if space is not None:
                attrs["memory_space"] = space
            ops.append(ArgumentOp(name, "real", attrs))
        arg_tables.append(ArgumentTableOp(table, "scheme", ops))
    return builtin.ModuleOp([TablePropertiesOp("m", "scheme", arg_tables)])


def _findings(tables):
    residency = {}
    build_meta_module_from_source(_SOURCE, "m.F90", None, residency)
    return [(f.level, f.table_name, f.message) for f in
            compare_memory_space(_meta_module(tables), residency, "m.F90")]


def test_agreement_is_silent():
    assert _findings({"m_run": {"a": "device", "b": None}}) == []


def test_device_use_with_silent_meta_is_a_note():
    # Stage 2 derives memory_space = device with --directive acc.
    (level, table, message), = _findings({"m_run": {"a": None}})
    assert (level, table) == ("note", "m_run")
    assert "'a' is used on the device (present, m.F90:" in message
    assert "derived with --directive acc" in message


def test_device_use_with_meta_host_warns():
    (level, _, message), = _findings({"m_run": {"a": "host"}})
    assert level == "warning" and "says memory_space = host" in message


def test_meta_device_never_used_on_device_warns():
    (level, _, message), = _findings({"m_run": {"a": "device", "b": "device"}})
    assert level == "warning"
    assert "'b' has memory_space = device in .meta, but" in message


def test_either_is_a_note():
    (level, _, message), = _findings({"m_run": {"a": "device", "c": None}})
    assert level == "note" and "'c' is copied by the scheme itself (copyin" in message


def test_either_with_meta_device_is_silent():
    assert _findings({"m_run": {"a": "device", "c": "device"}}) == []


def test_unified_not_compared():
    assert _findings({"m_run": {"a": "unified", "b": "unified"}}) == []


def test_derived_type_is_a_note():
    tables = {"m_run": {"a": "device", "gas": None}}
    (level, _, message), = _findings(tables)
    assert level == "note" and "'gas' is a derived type" in message


def test_dispatcher_without_acc_warns():
    (level, table, message), = _findings({"m_dispatch": {"a": "device"}})
    assert (level, table) == ("warning", "m_dispatch")
    assert "calls m_kernel, which does" in message


def test_no_acc_with_meta_device_is_a_note():
    (level, _, message), = _findings({"m_host": {"a": "device"}})
    assert level == "note" and "comes from .meta only" in message


def test_no_acc_without_meta_device_is_silent():
    assert _findings({"m_host": {"a": None}}) == []


def test_worker_prints_notes_only_at_verbose_2(tmp_path):
    meta = tmp_path / "m.meta"
    meta.write_text(
        "[ccpp-table-properties]\n  name = m\n  type = scheme\n"
        "[ccpp-arg-table]\n  name = m_run\n  type = scheme\n"
        "[ n ]\n  standard_name = n\n  units = 1\n  type = integer\n"
        "  dimensions = ()\n  intent = in\n"
        "[ a ]\n  standard_name = a\n  units = 1\n  type = real\n"
        "  dimensions = (n)\n  intent = inout\n  memory_space = device\n"
        "[ c ]\n  standard_name = c\n  units = 1\n  type = real\n"
        "  dimensions = (n)\n  intent = inout\n"
    )
    f90 = tmp_path / "m.F90"
    f90.write_text(
        "module m\ncontains\n  subroutine m_run(n, a, c)\n"
        "    integer, intent(in) :: n\n    real, intent(inout) :: a(:), c(:)\n"
        "    !$acc data present(a) copyin(c)\n    !$acc end data\n"
        "  end subroutine\nend module\n"
    )
    quiet = _validate_fortran_source(str(meta), str(f90), {}, 1)
    detailed = _validate_fortran_source(str(meta), str(f90), {}, 2)
    assert "copied by the scheme" not in quiet
    assert "m_run: 'c' is copied by the scheme itself (copyin" in detailed


def test_real_kessler_example_agrees_with_meta():
    # kessler_run holds its own kernels (no dispatcher): the derived
    # residency equals kessler.meta's memory_space = device list.
    out = _validate_fortran_source(
        "examples/kessler/scheme/kessler.meta", "examples/kessler/scheme/kessler.F90", {}, 2
    )
    assert "kessler_run" not in out


# ── derived type with memory_space = device ──────────────────────────────────

def _build(tmp_path, ddt_space: str, table_type: str = "scheme"):
    meta = tmp_path / "s.meta"
    meta.write_text(
        f"[ccpp-table-properties]\n  name = s\n  type = {table_type}\n"
        f"[ccpp-arg-table]\n  name = s_run\n  type = {table_type}\n"
        "[ gas ]\n  standard_name = gas_object\n  units = none\n"
        f"  type = gas_t\n  dimensions = ()\n  intent = inout\n{ddt_space}"
    )
    frontend = ccppXML()
    return [frontend.build_meta_ir(m, meta_file_path=str(meta))
            for m in parse_meta_file(str(meta), table_type == "scheme")]


def test_derived_type_on_device_is_an_error(tmp_path):
    with pytest.raises(CcppInputError, match=r"'s_run' argument 'gas' is a derived type \(gas_t\)"):
        _build(tmp_path, "  memory_space = device\n")


def test_derived_type_on_host_is_fine(tmp_path):
    assert _build(tmp_path, "")


def test_omp_wording():
    src = (
        "module m\ncontains\n  subroutine m_run(n, a)\n"
        "    integer, intent(in) :: n\n    real, intent(inout) :: a(:)\n"
        "    integer :: i\n    !$omp target teams distribute parallel do\n"
        "    do i = 1, n\n      a(i) = 0.\n    end do\n"
        "  end subroutine\nend module\n"
    )
    residency = {}
    build_meta_module_from_source(src, "m.F90", None, residency, "omp")
    (level, _, message), = [
        (f.level, f.table_name, f.message) for f in
        compare_memory_space(_meta_module({"m_run": {"a": None}}), residency, "m.F90", "omp")
    ]
    assert level == "note"
    assert "'a' is copied by the scheme itself (implicit, m.F90:7)" in message
    assert "derived with --directive omp" in message
