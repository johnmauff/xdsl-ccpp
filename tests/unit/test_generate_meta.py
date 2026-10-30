"""Tests for ccpp_generate_meta — .meta skeleton generation from Fortran source."""
from __future__ import annotations

import pytest
from xdsl.dialects import builtin

from xdsl_ccpp.dialects.ccpp import ArgumentOp, ArgumentTableOp, TablePropertiesOp
from xdsl_ccpp.tools.ccpp_generate_meta import (
    _is_ccpp_entry,
    generate_meta_for_file,
    meta_from_module,
)
from xdsl_ccpp.util.optional_deps import fparser_available


# ── helpers ───────────────────────────────────────────────────────────────────

requires_fparser = pytest.mark.skipif(
    not fparser_available(),
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
    def test_register_suffix(self):
        # dup-meta-shadow-elim (BACKLOG.md), Phase 7: found via
        # examples/advection's real cld_liq_register/cld_ice_register --
        # `register` is a genuine CCPP lifecycle phase (suite_cap.py's own
        # real cap generator already recognises it, `("_register", False):
        # "register"`), just missing from this tool's own suffix list, so
        # meta_from_module would silently drop a scheme's whole _register
        # arg-table block.
        assert _is_ccpp_entry("cld_liq_register")

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


# ── Phase 4: real values override stubs when present ──────────────────────────
# dup-meta-shadow-elim (BACKLOG.md). standard_name/units/long_name/
# memory_space come straight from an ArgumentOp's own property (set by a
# !$ccpp tag or a real device-residency directive, Phases 1-2) when present;
# stub fallback remains for standard_name/units only -- long_name/
# memory_space are legitimately sparse and simply omitted otherwise.

class TestMetaFromModuleRealValues:
    def test_real_standard_name_and_units_used_instead_of_stubs(self):
        module = _make_module("my_scheme", [
            ("my_scheme_run", [
                _make_arg("qv", "real", intent="inout",
                          standard_name="water_vapor_mixing_ratio", units="kg kg-1"),
            ]),
        ])
        out = meta_from_module(module)
        assert "  standard_name = water_vapor_mixing_ratio" in out
        assert "  units = kg kg-1" in out
        assert "std_name_001" not in out
        assert "enter_units" not in out

    def test_missing_standard_name_still_falls_back_to_stub(self):
        module = _make_module("my_scheme", [
            ("my_scheme_run", [_make_arg("qv", "real", intent="inout")]),
        ])
        out = meta_from_module(module)
        assert "  standard_name = std_name_001" in out
        assert "  units = enter_units" in out

    def test_long_name_emitted_when_present(self):
        module = _make_module("my_scheme", [
            ("my_scheme_run", [
                _make_arg("data", "real", intent="inout", long_name="per-thread data array"),
            ]),
        ])
        out = meta_from_module(module)
        assert "  long_name = per-thread data array" in out

    def test_long_name_omitted_not_stubbed_when_absent(self):
        module = _make_module("my_scheme", [
            ("my_scheme_run", [_make_arg("data", "real", intent="inout")]),
        ])
        out = meta_from_module(module)
        assert "long_name" not in out

    def test_memory_space_emitted_when_present(self):
        module = _make_module("my_scheme", [
            ("my_scheme_run", [
                _make_arg("temp", "real", intent="inout", memory_space="device"),
            ]),
        ])
        out = meta_from_module(module)
        assert "  memory_space = device" in out

    def test_memory_space_omitted_not_stubbed_when_absent(self):
        module = _make_module("my_scheme", [
            ("my_scheme_run", [_make_arg("temp", "real", intent="inout")]),
        ])
        out = meta_from_module(module)
        assert "memory_space" not in out

    def test_dependencies_emitted_for_matching_table_name(self):
        module = _make_module("my_scheme", [
            ("my_scheme_run", [_make_arg("x", "real", intent="in")]),
        ])
        out = meta_from_module(module, dependencies={"my_scheme": ["util.F90", "other.F90"]})
        assert "  dependencies = util.F90,other.F90" in out

    def test_no_dependencies_line_when_map_omits_this_table(self):
        module = _make_module("my_scheme", [
            ("my_scheme_run", [_make_arg("x", "real", intent="in")]),
        ])
        out = meta_from_module(module, dependencies={"some_other_scheme": ["util.F90"]})
        assert "dependencies" not in out

    def test_no_dependencies_line_when_dependencies_arg_omitted(self):
        # Default behavior, matching pre-Phase-4 output exactly.
        module = _make_module("my_scheme", [
            ("my_scheme_run", [_make_arg("x", "real", intent="in")]),
        ])
        out = meta_from_module(module)
        assert "dependencies" not in out


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

    def test_ccpp_tag_flows_through_to_real_standard_name_and_units(self):
        out = self._build("""
module my_scheme
  implicit none
contains
  subroutine my_scheme_run(qv)
    !$ccpp [qv] standard_name = water_vapor_mixing_ratio
    !$ccpp [qv] units = kg kg-1
    real, intent(inout) :: qv
  end subroutine
end module my_scheme
""")
        assert "  standard_name = water_vapor_mixing_ratio" in out
        assert "  units = kg kg-1" in out
        assert "std_name_001" not in out

    def test_real_acc_directive_flows_through_to_memory_space(self):
        out = self._build("""
module my_scheme
  implicit none
contains
  subroutine my_scheme_run(temp)
    real, intent(inout) :: temp
    !$acc parallel loop present(temp)
  end subroutine
end module my_scheme
""")
        assert "  memory_space = device" in out

    def test_arbitrary_tag_key_flows_through_generically(self):
        # dup-meta-shadow-elim (BACKLOG.md), Phase 7: advection's real
        # .meta files need fields beyond the original four
        # (standard_name/units/long_name/memory_space) -- advected/
        # constituent/protected/state_variable/default_value among them.
        # None of these need their own line of code in the forwarding
        # path any more; any ArgumentOp-recognised !$ccpp tag key reaches
        # the generated .meta verbatim.
        out = self._build("""
module cld_liq
  implicit none
contains
  subroutine cld_liq_run(cld_liq_array)
    real, intent(inout) :: cld_liq_array
    !$ccpp [cld_liq_array] standard_name = cloud_liquid_dry_mixing_ratio &
    !$ccpp                 advected = .true. &
    !$ccpp                 default_value = 0.0_kind_phys
  end subroutine
end module cld_liq
""")
        assert "  advected = True" in out
        assert "  default_value = 0.0_kind_phys" in out

    def test_unrecognised_tag_key_warns_and_is_dropped(self, capsys):
        from xdsl_ccpp.dialects.ccpp import ArgumentOp

        out = self._build("""
module my_scheme
  implicit none
contains
  subroutine my_scheme_run(qv)
    real, intent(inout) :: qv
    !$ccpp [qv] standard_name = water_vapor_mixing_ratio
    !$ccpp [qv] totally_bogus_key = oops
  end subroutine
end module my_scheme
""")
        assert "totally_bogus_key" not in out
        assert "oops" not in out
        assert "standard_name = water_vapor_mixing_ratio" in out
        err = capsys.readouterr().err
        assert "unrecognised !$ccpp tag key" in err
        assert "totally_bogus_key" in err
        assert "'qv'" in err
        assert "totally_bogus_key" not in ArgumentOp.KNOWN_PROPS

    def test_register_entry_point_is_not_silently_dropped(self):
        # dup-meta-shadow-elim (BACKLOG.md), Phase 7: found while building
        # examples/advection_nometa -- cld_liq_register/cld_ice_register
        # are real entry points (constituent registration), but
        # `_CCPP_ENTRY_SUFFIXES` lacked "_register" entirely, so
        # meta_from_module's filter_entries=True default silently dropped
        # the whole arg-table block. Scoped only to this .meta-from-
        # tagged-source convenience tool -- the real cap generator
        # (suite_cap.py) already recognised `_register` correctly, which
        # is why examples/advection (hand-authored .meta, never passes
        # through this tool) was never affected.
        out = self._build("""
module cld_liq
  implicit none
contains
  subroutine cld_liq_register(dyn_const, errmsg, errflg)
    use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t
    type(ccpp_constituent_properties_t), allocatable, intent(out) :: dyn_const(:)
    !$ccpp [dyn_const] standard_name = dynamic_constituents_for_cld_liq
    !$ccpp [dyn_const] units = none
    character(len=512), intent(out) :: errmsg
    integer, intent(out) :: errflg
  end subroutine cld_liq_register
end module cld_liq
""")
        assert "name = cld_liq_register" in out
        assert "standard_name = dynamic_constituents_for_cld_liq" in out
        assert "allocatable = True" in out

    def test_bare_colon_dim_names_tag_reproduces_deferred_shape(self):
        # dup-meta-shadow-elim (BACKLOG.md), Phase 7: found while building
        # examples/advection_nometa -- a `dim_names = :` tag (for a real
        # `dimensions = (:)` constituent-properties array, see
        # ArgumentOp's own dimensions-parsing fix in dialects/ccpp.py) must
        # reach the generated .meta as a literal "(:)", not fall back to a
        # stub dimension name (which a real suite then counts as a bogus
        # extra host variable -- confirmed via a real build failure).
        out = self._build("""
module cld_liq
  implicit none
contains
  subroutine cld_liq_register(dyn_const, errmsg, errflg)
    use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t
    type(ccpp_constituent_properties_t), allocatable, intent(out) :: dyn_const(:)
    !$ccpp [dyn_const] standard_name = dynamic_constituents_for_cld_liq &
    !$ccpp             dim_names = :
    character(len=512), intent(out) :: errmsg
    integer, intent(out) :: errflg
  end subroutine cld_liq_register
end module cld_liq
""")
        assert "dimensions = (:)" in out


# ── Phase 4: generate_meta_for_file's --root-dir dependency wiring ────────────

@requires_fparser
class TestGenerateMetaForFileRootDir:
    def test_no_root_dir_means_no_dependencies_line(self):
        out = generate_meta_for_file("examples/ddthost/scheme/make_ddt.F90")
        assert "dependencies" not in out

    def test_real_root_dir_resolves_real_dependency(self):
        # Locks in the real, already-verified result from Phase 3: ddt2.F90
        # is a genuine dependency; host_ccpp_ddt.F90 (also USEd, but a DDT
        # table) correctly is not.
        out = generate_meta_for_file(
            "examples/ddthost/scheme/make_ddt.F90", root_dir="examples/ddthost"
        )
        assert "  dependencies = ddt2.F90" in out
        assert "host_ccpp_ddt" not in out

    def test_unresolvable_dependency_reported_as_error_not_crash(self, tmp_path, capsys):
        f = tmp_path / "scheme.F90"
        f.write_text(
            "module scheme\n"
            "  use totally_unknown_module\n"
            "contains\n"
            "  subroutine scheme_run(x)\n"
            "    real, intent(in) :: x\n"
            "  end subroutine\n"
            "end module scheme\n"
        )
        result = generate_meta_for_file(str(f), root_dir=str(tmp_path))
        assert result is None
        assert "totally_unknown_module" in capsys.readouterr().err
