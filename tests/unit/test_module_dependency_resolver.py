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


# ── scan_fortran_source / source_closure (scheme-io-capture-host-module-
#    schemes: the capture drivers' sources, and MPI use) ─────────────────────

from xdsl_ccpp.transforms.module_dependency_resolver import (  # noqa: E402
    scan_fortran_source,
    source_closure,
)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return str(path)


def test_scan_reads_statements_a_whole_file_parse_rejects(tmp_path):
    # USE_CONTIGUOUS is a macro (coords_1d.F90): the file does not parse
    # as Fortran, its statements still do.
    f = _write(tmp_path / "c.F90", (
        "module Coords\n"
        "  use, intrinsic :: iso_fortran_env, only: &\n"
        "       real64\n"
        "  USE Shr_Kind_Mod ! comment\n"
        "  interface c\n"
        "     module procedure c_one\n"
        "  end interface\n"
        "contains\n"
        "  subroutine c_one(x)\n"
        "    real(real64), USE_CONTIGUOUS intent(in) :: x(:)\n"
        "    include 'mpif.h'\n"
        "    user = 1\n"
        "    msg = 'use foo'\n"
        "  end subroutine\n"
        "end module\n"
    ))
    facts = scan_fortran_source(f)
    assert facts.uses == {"iso_fortran_env", "shr_kind_mod"}
    assert facts.modules == {"coords"}
    assert facts.includes == {"mpif.h"}


def test_scan_with_defines_leaves_out_excluded_branches(tmp_path):
    f = _write(tmp_path / "m.F90", (
        "module m\n#ifdef SPMD\n  use mpi\n#else\n  use serial_stub\n#endif\nend module\n"
    ))
    assert scan_fortran_source(f).uses == {"mpi", "serial_stub"}
    assert scan_fortran_source(f, {}).uses == {"serial_stub"}
    assert scan_fortran_source(f, {"SPMD": None}).uses == {"mpi"}


def _repo(tmp_path):
    root = tmp_path / "repo"
    scheme = _write(root / "schemes" / "s.F90",
                    "module s\n  use ccpp_kinds\n  use util_a\n  use host_only\nend module\n")
    _write(root / "utils" / "util_a.F90", "module util_a\n  use util_b\nend module\n")
    _write(root / "utils" / "b.F90", "module util_b\n  use, intrinsic :: iso_c_binding\nend module\n")
    _write(root / "utils" / "unused.F90", "module unused\nend module\n")
    return str(root), scheme


def test_closure_follows_uses_through_the_tree(tmp_path):
    root, scheme = _repo(tmp_path)
    closure = source_closure([scheme], root, provided={"ccpp_kinds"})
    assert [os.path.relpath(p, root) for p in closure.sources] == [
        "schemes/s.F90", "utils/util_a.F90", "utils/b.F90",
    ]
    assert closure.unresolved == {"host_only": "used by s.F90"}
    assert closure.mpi == []


def test_closure_prefers_a_file_already_in_it_and_reports_ambiguity(tmp_path):
    root, scheme = _repo(tmp_path)
    _write(tmp_path / "repo" / "other" / "util_b.F90", "module util_b\nend module\n")
    dup = source_closure([scheme], root, provided={"ccpp_kinds", "host_only"})
    assert "util_b" in dup.unresolved and "defined in 2 files" in dup.unresolved["util_b"]
    # A start file (e.g. a metadata dependency) that defines the module wins.
    named = os.path.join(root, "utils", "b.F90")
    picked = source_closure([scheme, named], root, provided={"ccpp_kinds", "host_only"})
    assert picked.unresolved == {}
    assert named in picked.sources


def test_closure_finds_mpi_in_a_used_module(tmp_path):
    root, scheme = _repo(tmp_path)
    _write(tmp_path / "repo" / "utils" / "b.F90",
           "module util_b\ncontains\n subroutine r()\n  use mpi, only: mpi_sum\n end subroutine\nend module\n")
    _write(tmp_path / "repo" / "utils" / "util_a.F90",
           "module util_a\n  use util_b\n  include 'mpif.h'\nend module\n")
    closure = source_closure([scheme], root, provided={"ccpp_kinds"})
    found = sorted((os.path.basename(p), what) for p, what in closure.mpi)
    assert found == [("b.F90", "use mpi"), ("util_a.F90", "include 'mpif.h'")]
    assert "mpi" not in closure.unresolved


def test_closure_without_a_root_resolves_only_the_given_files(tmp_path):
    root, scheme = _repo(tmp_path)
    closure = source_closure([scheme], None, provided={"ccpp_kinds"})
    assert closure.sources == [scheme]
    assert set(closure.unresolved) == {"util_a", "host_only"}
