"""Tests for ccpp_generate_meta — .meta skeleton generation from Fortran source."""
from __future__ import annotations

import pytest
from xdsl.dialects import builtin

from xdsl_ccpp.dialects.ccpp import ArgumentOp, ArgumentTableOp, TablePropertiesOp
from xdsl_ccpp.tools.ccpp_generate_meta import _is_ccpp_entry, meta_from_module


# ── helpers ───────────────────────────────────────────────────────────────────

def _fparser_available() -> bool:
    try:
        import fparser.two.Fortran2003  # noqa: F401
        return True
    except ImportError:
        return False


requires_fparser = pytest.mark.skipif(
    not _fparser_available(),
    reason="fparser not installed — skipping Fortran-source tests",
)


def _make_arg(name: str, type_: str, **kwargs) -> ArgumentOp:
    """Build an ArgumentOp from keyword attrs; always includes 'type' in attrs dict."""
    attrs = {"type": type_, **kwargs}
    return ArgumentOp(name, type_, attrs)


def _make_module(scheme_name: str, entry_points: list[tuple[str, list[ArgumentOp]]]) -> builtin.ModuleOp:
    """Build a minimal MLIR module with one TablePropertiesOp."""
    arg_tables = [
        ArgumentTableOp(ep_name, "scheme", arg_ops)
        for ep_name, arg_ops in entry_points
    ]
    return builtin.ModuleOp([TablePropertiesOp(scheme_name, "scheme", arg_tables)])


# ── entry-point name detection ────────────────────────────────────────────────

class TestIsCcppEntry:
    def test_run_suffix(self):
        assert _is_ccpp_entry("temp_adjust_run")

    def test_init_suffix(self):
        assert _is_ccpp_entry("scheme_init")

    def test_finalize_suffix(self):
        assert _is_ccpp_entry("scheme_finalize")

    def test_final_suffix(self):
        assert _is_ccpp_entry("scheme_final")

    def test_timestep_init(self):
        assert _is_ccpp_entry("scheme_timestep_init")

    def test_timestep_final(self):
        assert _is_ccpp_entry("scheme_timestep_final")

    def test_non_ccpp_helper(self):
        assert not _is_ccpp_entry("helper_subroutine")

    def test_case_insensitive(self):
        assert _is_ccpp_entry("Scheme_Run")


# ── serializer unit tests (no fparser needed) ─────────────────────────────────

class TestMetaFromModule:
    def test_table_properties_header(self):
        module = _make_module("temp_adjust", [
            ("temp_adjust_run", [_make_arg("temp", "real", intent="inout")]),
        ])
        out = meta_from_module(module)
        assert "[ccpp-table-properties]" in out
        assert "  name = temp_adjust" in out
        assert "  type = scheme" in out

    def test_arg_table_header(self):
        module = _make_module("temp_adjust", [
            ("temp_adjust_run", [_make_arg("temp", "real", intent="inout")]),
        ])
        out = meta_from_module(module)
        assert "[ccpp-arg-table]" in out
        assert "  name = temp_adjust_run" in out

    def test_scalar_arg_fields(self):
        module = _make_module("my_scheme", [
            ("my_scheme_run", [_make_arg("ncol", "integer", intent="in")]),
        ])
        out = meta_from_module(module)
        assert "[ ncol ]" in out
        assert "  standard_name = std_name_001" in out
        assert "  units = enter_units" in out
        assert "  type = integer" in out
        assert "  dimensions = ()" in out
        assert "  intent = in" in out

    def test_array_arg_dim_stubs(self):
        module = _make_module("my_scheme", [
            ("my_scheme_run", [_make_arg("data", "real", dimensions="(dim1, dim2)", intent="in")]),
        ])
        out = meta_from_module(module)
        assert "  dimensions = (dim1, dim2)" in out

    def test_kind_field_emitted(self):
        module = _make_module("my_scheme", [
            ("my_scheme_run", [_make_arg("temp", "real", kind="kind_phys", intent="in")]),
        ])
        out = meta_from_module(module)
        assert "  kind = kind_phys" in out

    def test_optional_field_emitted(self):
        module = _make_module("my_scheme", [
            ("my_scheme_run", [_make_arg("diag", "real", intent="out", optional="True")]),
        ])
        out = meta_from_module(module)
        assert "  optional = True" in out

    def test_stub_counter_increments_across_args(self):
        module = _make_module("my_scheme", [
            ("my_scheme_run", [
                _make_arg("a", "real", intent="in"),
                _make_arg("b", "real", intent="in"),
            ]),
        ])
        out = meta_from_module(module)
        assert "std_name_001" in out
        assert "std_name_002" in out

    def test_filters_non_ccpp_subroutines(self):
        module = _make_module("my_scheme", [
            ("my_scheme_run", [_make_arg("x", "real", intent="in")]),
            ("helper_sub",    [_make_arg("y", "real", intent="in")]),
        ])
        out = meta_from_module(module)
        assert "my_scheme_run" in out
        assert "helper_sub" not in out

    def test_empty_when_no_ccpp_entries(self):
        module = _make_module("my_scheme", [
            ("helper_sub", [_make_arg("x", "real", intent="in")]),
        ])
        out = meta_from_module(module)
        assert out.strip() == ""

    def test_multiple_entry_points_emitted(self):
        module = _make_module("my_scheme", [
            ("my_scheme_init",     [_make_arg("flag", "logical", intent="in")]),
            ("my_scheme_run",      [_make_arg("temp", "real", intent="inout")]),
            ("my_scheme_finalize", []),
        ])
        out = meta_from_module(module)
        assert "my_scheme_init" in out
        assert "my_scheme_run" in out
        assert "my_scheme_finalize" in out

    def test_filter_entries_false_includes_helpers(self):
        module = _make_module("my_scheme", [
            ("my_scheme_run", [_make_arg("x", "real", intent="in")]),
            ("helper_sub",    [_make_arg("y", "real", intent="in")]),
        ])
        out = meta_from_module(module, filter_entries=False)
        assert "my_scheme_run" in out
        assert "helper_sub" in out

    def test_no_trailing_blank_lines(self):
        module = _make_module("my_scheme", [
            ("my_scheme_run", [_make_arg("x", "real", intent="in")]),
        ])
        out = meta_from_module(module)
        assert out.endswith("\n")
        assert not out.endswith("\n\n")


# ── integration tests (require fparser) ───────────────────────────────────────

@requires_fparser
class TestFromFortranSource:
    def _build(self, source: str) -> str:
        from xdsl_ccpp.transforms.fparser2_to_meta import build_meta_module_from_source
        return meta_from_module(build_meta_module_from_source(source))

    def test_basic_run_subroutine(self):
        out = self._build("""
module temp_adjust
  implicit none
contains
  subroutine temp_adjust_run(ncol, temp, errmsg, errflg)
    integer, intent(in) :: ncol
    real(kind=kind_phys), intent(inout) :: temp(:)
    character(len=512), intent(out) :: errmsg
    integer, intent(out) :: errflg
  end subroutine temp_adjust_run
end module temp_adjust
""")
        assert "[ccpp-table-properties]" in out
        assert "  name = temp_adjust" in out
        assert "[ ncol ]" in out
        assert "[ temp ]" in out
        assert "  type = integer" in out
        assert "  intent = inout" in out
        assert "  kind = kind_phys" in out
        assert "dimensions = (dim1)" in out

    def test_non_ccpp_subroutine_excluded(self):
        out = self._build("""
module my_scheme
  implicit none
contains
  subroutine my_scheme_run(x)
    real, intent(in) :: x
  end subroutine
  subroutine helper(y)
    real, intent(in) :: y
  end subroutine
end module my_scheme
""")
        assert "my_scheme_run" in out
        assert "helper" not in out

    def test_scalar_has_empty_dimensions(self):
        out = self._build("""
module my_scheme
  implicit none
contains
  subroutine my_scheme_run(n)
    integer, intent(in) :: n
  end subroutine
end module my_scheme
""")
        assert "  dimensions = ()" in out

    def test_2d_array_gets_two_dim_stubs(self):
        out = self._build("""
module my_scheme
  implicit none
contains
  subroutine my_scheme_run(arr)
    real, intent(in) :: arr(:,:)
  end subroutine
end module my_scheme
""")
        assert "dimensions = (dim1, dim2)" in out

    def test_optional_arg(self):
        out = self._build("""
module my_scheme
  implicit none
contains
  subroutine my_scheme_run(x, y)
    real, intent(in) :: x
    real, optional, intent(out) :: y
  end subroutine
end module my_scheme
""")
        assert "  optional = True" in out

    def test_stubs_are_numbered(self):
        out = self._build("""
module my_scheme
  implicit none
contains
  subroutine my_scheme_run(a, b, c)
    real, intent(in) :: a
    real, intent(in) :: b
    real, intent(out) :: c
  end subroutine
end module my_scheme
""")
        assert "std_name_001" in out
        assert "std_name_002" in out
        assert "std_name_003" in out
