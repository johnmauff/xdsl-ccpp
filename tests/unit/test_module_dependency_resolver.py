"""Unit tests for module_dependency_resolver -- deriving a scheme's
`dependencies =` field from its own `USE` statements.

dup-meta-shadow-elim (BACKLOG.md), Phase 3. Tests cover the module-name
index builder (including the real ambiguity it's specifically meant to
guard against), the USE-statement extractor, and resolve_scheme_
dependencies' exclusion rules (framework, intrinsic, self-reference,
DDT/HOST tables) against both synthetic fixtures and real files in
examples/ -- including a case where the real, already-authored `.meta`
revealed a rule (DDT/HOST exclusion) that wasn't in the original design
sketch until checked against real content.
"""

import os

import pytest

pytest.importorskip("fparser", reason="fparser not installed")

from xdsl_ccpp.transforms.module_dependency_resolver import (
    build_module_index,
    extract_used_modules,
    resolve_scheme_dependencies,
)


# ── build_module_index ───────────────────────────────────────────────────────

def test_finds_module_defined_in_file(tmp_path):
    (tmp_path / "foo.F90").write_text("module foo\nend module foo\n")
    index = build_module_index(str(tmp_path))
    assert "foo" in index
    assert os.path.abspath(index["foo"]) == os.path.abspath(str(tmp_path / "foo.F90"))


def test_module_name_lowercased(tmp_path):
    (tmp_path / "foo.F90").write_text("module FOO\nend module FOO\n")
    index = build_module_index(str(tmp_path))
    assert "foo" in index


def test_ambiguous_module_raises(tmp_path):
    (tmp_path / "a.F90").write_text("module dup\nend module dup\n")
    (tmp_path / "b.F90").write_text("module dup\nend module dup\n")
    with pytest.raises(ValueError, match="defined in more than one file"):
        build_module_index(str(tmp_path))


def test_unparseable_file_skipped_not_fatal(tmp_path):
    (tmp_path / "bad.F90").write_text("this is not valid fortran {{{")
    (tmp_path / "good.F90").write_text("module good\nend module good\n")
    index = build_module_index(str(tmp_path))
    assert "good" in index


# ── extract_used_modules ──────────────────────────────────────────────────────

def test_extracts_module_level_and_subroutine_level_use(tmp_path):
    f = tmp_path / "m.F90"
    f.write_text(
        "module m\n"
        "  use ccpp_kinds\n"
        "contains\n"
        "  subroutine m_run()\n"
        "    use some_util, only: helper\n"
        "  end subroutine\n"
        "end module m\n"
    )
    used = extract_used_modules(str(f))
    assert used == {"ccpp_kinds", "some_util"}


# ── resolve_scheme_dependencies: exclusion rules (synthetic) ────────────────

def test_framework_modules_excluded(tmp_path):
    f = tmp_path / "scheme.F90"
    f.write_text(
        "module scheme\n"
        "  use ccpp_kinds\n"
        "  use ccpp_scheme_utils\n"
        "  use ccpp_constituent_prop_mod\n"
        "end module scheme\n"
    )
    assert resolve_scheme_dependencies(str(f), str(tmp_path)) == []


def test_intrinsic_modules_excluded(tmp_path):
    f = tmp_path / "scheme.F90"
    f.write_text("module scheme\n  use openacc\n  use iso_c_binding\nend module scheme\n")
    assert resolve_scheme_dependencies(str(f), str(tmp_path)) == []


def test_self_use_excluded(tmp_path):
    # A file re-USE-ing its own module name (unusual but not impossible in
    # a submodule-style file) must never list itself as a dependency.
    f = tmp_path / "scheme.F90"
    f.write_text("module scheme\n  use scheme\nend module scheme\n")
    assert resolve_scheme_dependencies(str(f), str(tmp_path)) == []


def test_ordinary_utility_module_included(tmp_path):
    (tmp_path / "util.F90").write_text("module util\nend module util\n")
    f = tmp_path / "scheme.F90"
    f.write_text("module scheme\n  use util\nend module scheme\n")
    assert resolve_scheme_dependencies(str(f), str(tmp_path)) == ["util.F90"]


def test_ddt_type_module_excluded(tmp_path):
    # Confirmed against real examples/ddthost/scheme/make_ddt.F90: a DDT
    # type used as an argument type is NOT listed in the scheme's own
    # dependencies= -- it's included unconditionally via a separate
    # mechanism regardless of which scheme uses it.
    (tmp_path / "my_ddt.F90").write_text("module my_ddt\nend module my_ddt\n")
    (tmp_path / "my_ddt.meta").write_text(
        "[ccpp-table-properties]\n  name = my_type\n  type = ddt\n"
        "[ccpp-arg-table]\n  name = my_type\n  type = ddt\n"
    )
    f = tmp_path / "scheme.F90"
    f.write_text("module scheme\n  use my_ddt\nend module scheme\n")
    assert resolve_scheme_dependencies(str(f), str(tmp_path)) == []


def test_host_type_module_excluded(tmp_path):
    (tmp_path / "my_host.F90").write_text("module my_host\nend module my_host\n")
    (tmp_path / "my_host.meta").write_text(
        "[ccpp-table-properties]\n  name = my_host\n  type = host\n"
        "[ccpp-arg-table]\n  name = my_host\n  type = host\n"
    )
    f = tmp_path / "scheme.F90"
    f.write_text("module scheme\n  use my_host\nend module scheme\n")
    assert resolve_scheme_dependencies(str(f), str(tmp_path)) == []


def test_module_with_no_meta_at_all_is_ordinary_dependency(tmp_path):
    # No sibling .meta at all (a plain Fortran utility module, like real
    # gw_utils.F90/coords_1d.F90) -- nothing to classify as DDT/HOST, so
    # it's an ordinary dependency.
    (tmp_path / "plain_util.F90").write_text("module plain_util\nend module plain_util\n")
    f = tmp_path / "scheme.F90"
    f.write_text("module scheme\n  use plain_util\nend module scheme\n")
    assert resolve_scheme_dependencies(str(f), str(tmp_path)) == ["plain_util.F90"]


def test_unresolvable_module_raises(tmp_path):
    f = tmp_path / "scheme.F90"
    f.write_text("module scheme\n  use totally_unknown_module\nend module scheme\n")
    with pytest.raises(ValueError, match="totally_unknown_module"):
        resolve_scheme_dependencies(str(f), str(tmp_path))


def test_relative_path_computed_from_own_directory(tmp_path):
    sub = tmp_path / "scheme_dir"
    sub.mkdir()
    (tmp_path / "shared_util.F90").write_text("module shared_util\nend module shared_util\n")
    f = sub / "scheme.F90"
    f.write_text("module scheme\n  use shared_util\nend module scheme\n")
    deps = resolve_scheme_dependencies(str(f), str(tmp_path))
    assert deps == [os.path.join("..", "shared_util.F90")]


# ── real-file regression tests ──────────────────────────────────────────────

def test_real_make_ddt_matches_known_dependency():
    # examples/ddthost/scheme/make_ddt.F90's own USE statements resolve to
    # exactly ddt2.F90 as a real dependency -- the real, already-authored
    # make_ddt.meta records the same ddt2.F90 (on its co-located DDT
    # table's own dependencies=, confirmed this session) -- and
    # specifically does NOT list host_ccpp_ddt.F90 (a real USE, but of a
    # DDT-type module), proving the DDT-exclusion rule matches real
    # capgen-v1 convention, not just a synthetic case.
    deps = resolve_scheme_dependencies(
        "examples/ddthost/scheme/make_ddt.F90", "examples/ddthost"
    )
    assert deps == ["ddt2.F90"]


def test_real_kessler_has_no_unresolved_extra_dependencies():
    # kessler.meta has no dependencies= line at all -- kessler.F90's own
    # USEs (ccpp_kinds, ccpp_scheme_utils, openacc) are all framework or
    # intrinsic, so the real answer is an empty list.
    assert resolve_scheme_dependencies(
        "examples/kessler/scheme/kessler.F90", "examples/kessler"
    ) == []
    assert resolve_scheme_dependencies(
        "examples/kessler/scheme/kessler_update.F90", "examples/kessler"
    ) == []


def test_whole_examples_tree_is_too_broad_a_root():
    # Real, confirmed finding this session: examples/ is ~20 independent
    # example projects reusing generic module names (e.g. 'data' defined
    # in both suite_allocate/ and instances/) -- scoping root_dir to the
    # whole examples/ tree must raise, not silently pick one.
    with pytest.raises(ValueError, match="defined in more than one file"):
        build_module_index("examples")
