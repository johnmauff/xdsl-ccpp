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


def test_scan_records_procedure_scopes_and_calls(tmp_path):
    f = _write(tmp_path / "q.F90", (
        "module q\n"
        "  use ccpp_kinds\n"
        "  interface stats\n"
        "     module procedure stats_a, stats_b\n"
        "  end interface\n"
        "  interface\n"
        "     subroutine ext(x)\n"
        "       use mpi\n"
        "     end subroutine ext\n"
        "  end interface\n"
        "contains\n"
        "  subroutine q_final(n)\n"
        "    if (n > 0) call summary(n)\n"
        "  end subroutine q_final\n"
        "  pure real(kind_phys) function f(x) result(y)\n"
        "    call obj%helper(x)\n"
        "  end function\n"
        "#if 0\n"
        "  subroutine gone()\n"
        "  end subroutine\n"
        "#endif\n"
        "end module q\n"
    ))
    scopes = {s.name: s for s in scan_fortran_source(f, {}).scopes}
    assert set(scopes) == {None, "stats", "q_final", "f"}  # no interface body
    assert scopes["stats"].calls == {"stats_a", "stats_b"}
    assert scopes["q_final"].calls == {"summary"}
    assert scopes["f"].calls == {"helper"}
    assert scopes[None].module == "q" and scopes[None].uses == {"ccpp_kinds"}


def test_mpi_reach_follows_calls_generics_and_module_scope(tmp_path):
    root = tmp_path / "repo"
    scheme = _write(root / "s.F90", (
        "module s\n  use util_mpi\ncontains\n"
        "  subroutine s_init()\n  end subroutine\n"
        "  subroutine s_run()\n    call stats()\n  end subroutine\n"
        "  subroutine s_final()\n    call helper()\n  end subroutine\n"
        "end module\n"))
    _write(root / "util_mpi.F90", (
        "module util_mpi\n  interface stats\n    module procedure stats_one\n"
        "  end interface\ncontains\n"
        "  subroutine stats_one()\n    call reduce()\n  end subroutine\n"
        "  subroutine reduce()\n    include 'mpif.h'\n  end subroutine\n"
        "end module\n"))
    _write(root / "h.F90", "module h_mod\n  use mpi_f08\ncontains\n"
                           "  subroutine helper()\n  end subroutine\nend module\n")
    _write(root / "s2.F90", "module s2\n  use h_mod\nend module\n")
    closure = source_closure([scheme, str(root / "s2.F90")], str(root), preproc_defs={})
    reach = closure.mpi_procedures
    assert "s_init" not in reach
    assert reach["s_run"] == ("s_run calls stats, which calls stats_one, which calls "
                              "reduce, which has include 'mpif.h' (util_mpi.F90)")
    assert reach["s_final"] == ("s_final calls helper, which is in module h_mod, "
                                "which has use mpi_f08 (h.F90)")


# ── scheme-io-capture-rte-kernel-variants: modules in several files ────────

from xdsl_ccpp.transforms.module_dependency_resolver import (  # noqa: E402
    accel_variant_pair,
)


def _kernels_repo(tmp_path):
    """RTE-RRTMGP's layout: a kernel module with a CPU version, an OpenACC
    version in accel/, and an API copy no build compiles; the OpenACC
    version alone uses a helper module."""
    root = tmp_path / "repo"
    scheme = _write(root / "schemes" / "s.F90", "module s\n  use mo_k\nend module\n")
    cpu = _write(root / "kernels" / "mo_k.F90", "module mo_k\nend module\n")
    gpu = _write(root / "kernels" / "accel" / "mo_k.F90",
                 "module mo_k\n  use mo_acc_util\nend module\n")
    api = _write(root / "kernels" / "api" / "mo_k.F90", "module mo_k\nend module\n")
    util = _write(root / "kernels" / "mo_acc_util.F90", "module mo_acc_util\nend module\n")
    return str(root), scheme, cpu, gpu, api, util


def test_accel_variant_pair_is_a_file_and_its_accel_copy():
    assert accel_variant_pair(["/k/accel/m.F90", "/k/m.F90"]) == ("/k/m.F90", "/k/accel/m.F90")
    assert accel_variant_pair(["/k/m.F90", "/k/api/m.F90"]) is None
    assert accel_variant_pair(["/k/m.F90", "/other/accel/m.F90"]) is None
    assert accel_variant_pair(["/k/m.F90", "/k/accel/n.F90"]) is None
    assert accel_variant_pair(["/k/m.F90", "/k/accel/m.F90", "/k/api/m.F90"]) is None


def test_closure_without_listed_files_leaves_three_copies_unresolved(tmp_path):
    root, scheme, *_ = _kernels_repo(tmp_path)
    closure = source_closure([scheme], root)
    assert "defined in 3 files" in closure.unresolved["mo_k"]
    assert closure.variants == {}


def test_closure_takes_the_listed_copy_of_a_module(tmp_path):
    root, scheme, cpu, _gpu, _api, _util = _kernels_repo(tmp_path)
    closure = source_closure([scheme], root, listed={cpu})
    assert closure.unresolved == {}
    assert closure.sources == [scheme, cpu]
    assert closure.variants == {}


def test_closure_turns_a_listed_cpu_gpu_pair_into_a_variant(tmp_path):
    root, scheme, cpu, gpu, _api, util = _kernels_repo(tmp_path)
    closure = source_closure([scheme], root, listed={cpu, gpu})
    assert closure.unresolved == {}
    assert closure.variants == {"mo_k": (cpu, gpu)}
    # Neither version is a common source; what the GPU version alone uses is.
    assert closure.sources == [scheme, util]


def test_closure_turns_a_pair_among_the_start_files_into_a_variant(tmp_path):
    # The metadata `dependencies` (start files) can name both versions.
    root, scheme, cpu, gpu, _api, util = _kernels_repo(tmp_path)
    closure = source_closure([scheme, cpu, gpu], root)
    assert closure.unresolved == {}
    assert closure.variants == {"mo_k": (cpu, gpu)}
    assert closure.sources == [scheme, util]


def test_closure_reports_two_needed_files_defining_one_module(tmp_path):
    root, scheme, cpu, _gpu, api, _util = _kernels_repo(tmp_path)
    closure = source_closure([scheme, cpu, api], root)
    assert closure.unresolved == {
        "mo_k": "defined in kernels/mo_k.F90, kernels/api/mo_k.F90, all needed by the scheme"
    }


# ── scheme-io-capture-share-code: other source trees ───────────────────────

def test_closure_looks_in_extra_roots_after_the_repository(tmp_path):
    root, scheme = _repo(tmp_path)
    share = tmp_path / "share"
    kind = _write(share / "shr_kind_mod.F90", "module shr_kind_mod\nend module\n")
    # A copy of a repository module there never wins over the repository's.
    _write(share / "util_a.F90", "module util_a\nend module\n")
    _write(tmp_path / "repo" / "utils" / "c.F90", "module util_c\n  use shr_kind_mod\nend module\n")
    _write(tmp_path / "repo" / "utils" / "util_a.F90",
           "module util_a\n  use util_b\n  use util_c\nend module\n")
    closure = source_closure([scheme], root, provided={"ccpp_kinds", "host_only"},
                             extra_roots=[str(share)])
    assert closure.unresolved == {}
    assert kind in closure.sources
    assert os.path.join(root, "utils", "util_a.F90") in closure.sources
    assert os.path.join(str(share), "util_a.F90") not in closure.sources


def test_closure_reports_what_an_extra_root_module_still_needs(tmp_path):
    root, scheme = _repo(tmp_path)
    share = tmp_path / "share"
    _write(share / "shr_log_mod.F90", "module shr_log_mod\n  use esmf\nend module\n")
    _write(tmp_path / "repo" / "utils" / "util_a.F90", "module util_a\n  use shr_log_mod\nend module\n")
    closure = source_closure([scheme], root, provided={"ccpp_kinds", "host_only"},
                             extra_roots=[str(share)])
    assert closure.unresolved == {"esmf": "used by shr_log_mod.F90"}


# ── scheme-io-capture-module-state-setup: module variables ─────────────────

from xdsl_ccpp.transforms.module_dependency_resolver import (  # noqa: E402
    module_state_access,
)


def _state_files(tmp_path):
    utils = _write(tmp_path / "utils.F90", (
        "module utils\n"
        "  use ccpp_kinds, only: kind_phys\n"
        "  integer, parameter :: nmax = 3\n"
        "  real(kind_phys) :: ml2, ccon = 0.\n"
        "  type :: props_t\n"
        "    real(kind_phys) :: comp\n"
        "  end type props_t\n"
        "  type(props_t), public :: props\n"
        "contains\n"
        "  subroutine utils_init(x)\n"
        "    real(kind_phys), intent(in) :: x\n"
        "    ml2 = x**2\n"
        "    call fill(props)\n"
        "  end subroutine utils_init\n"
        "  subroutine fill(p)\n"
        "    type(props_t), intent(out) :: p\n"
        "    p%comp = 1.\n"
        "  end subroutine fill\n"
        "  pure function scaled(y) result(z)\n"
        "    real(kind_phys), intent(in) :: y\n"
        "    real(kind_phys) :: z\n"
        "    z = y * ccon\n"
        "  end function scaled\n"
        "end module utils\n"
    ))
    scheme = _write(tmp_path / "s.F90", (
        "module s\n"
        "  use utils, only: lsq => ml2, props, scaled\n"
        "contains\n"
        "  subroutine s_run(a, b, msg)\n"
        "    real, intent(inout) :: a, b\n"
        "    character(len=*), intent(out) :: msg\n"
        "    real :: comp\n"
        "    msg = 'ml2 is unset'\n"
        "    a = lsq * props%comp + scaled(b)\n"
        "    comp = 1.\n"
        "  end subroutine s_run\n"
        "  subroutine s_shadow(ml2)\n"
        "    real, intent(in) :: ml2\n"
        "  end subroutine s_shadow\n"
        "end module s\n"
    ))
    return [scan_fortran_source(utils), scan_fortran_source(scheme)]


def test_scan_records_module_variables_declarations_and_assignments(tmp_path):
    facts = _state_files(tmp_path)
    module_scope = next(s for s in facts[0].scopes if s.name is None)
    # Not the parameter, not the derived type's component.
    assert module_scope.variables == {"ml2", "ccon", "props"}
    init = next(s for s in facts[0].scopes if s.name == "utils_init")
    assert init.assigns == {"ml2"} and init.passes == {"props"}
    run = next(s for s in facts[1].scopes if s.name == "s_run")
    s_module = next(s for s in facts[1].scopes if s.name is None)
    assert s_module.use_only == (
        ("utils", frozenset({("lsq", "ml2"), ("props", "props"), ("scaled", "scaled")})),)
    # Not the component after %, not the string's words.
    assert "comp" in run.refs  # the local comp = 1.
    assert "is" not in run.refs and "unset" not in run.refs
    assert run.assigns == {"msg", "a", "comp"}


def test_module_state_reads_follow_renames_calls_and_functions(tmp_path):
    facts = _state_files(tmp_path)
    reads = module_state_access(facts, "s_run")
    # lsq is ml2 renamed; scaled (a function) reads ccon.
    assert reads == {("utils", "ml2"): "s_run", ("utils", "props"): "s_run",
                     ("utils", "ccon"): "scaled"}
    # A dummy argument named like a module variable hides it.
    assert module_state_access(facts, "s_shadow") == {}


def test_module_state_sets_include_what_a_call_may_set(tmp_path):
    facts = _state_files(tmp_path)
    assert set(module_state_access(facts, "utils_init", "assigns")) == {("utils", "ml2")}
    assert set(module_state_access(facts, "utils_init", "sets")) == {
        ("utils", "ml2"), ("utils", "props")}


# ── scheme-io-capture-ddt-args: derived-type definitions ───────────────────

from xdsl_ccpp.transforms.module_dependency_resolver import (  # noqa: E402
    capture_layout,
    resolve_real_kind,
)


def _type_files(tmp_path):
    kinds = _write(tmp_path / "kinds.F90", (
        "module my_kinds\n"
        "  integer,parameter :: dp = selected_real_kind(12)\n"
        "  integer, parameter :: sp = selected_real_kind(6)\n"
        "end module my_kinds\n"
    ))
    types = _write(tmp_path / "types.F90", (
        "module my_types\n"
        "  use my_kinds, only: r8 => dp, sp\n"
        "  type, public :: flat_t\n"
        "    integer :: n = 0\n"
        "    real(r8), allocatable :: a(:,:)\n"
        "    real(r8), dimension(:), allocatable :: b\n"
        "    logical :: on(3)\n"
        "  contains\n"
        "    procedure :: reset\n"
        "    final :: done\n"
        "  end type flat_t\n"
        "  type :: hidden_t\n"
        "    private\n"
        "    real(r8) :: x\n"
        "  end type hidden_t\n"
        "  type, extends(flat_t) :: child_t\n"
        "    real(r8) :: y\n"
        "  end type child_t\n"
        "  type :: mixed_t\n"
        "    real(sp) :: s\n"
        "    real(r8), pointer :: p(:) => null()\n"
        "  end type mixed_t\n"
        "end module my_types\n"
    ))
    return [scan_fortran_source(kinds), scan_fortran_source(types)]


def test_scan_records_derived_type_definitions(tmp_path):
    facts = _type_files(tmp_path)
    types = {t.name: t for t in facts[1].types}
    assert set(types) == {"flat_t", "hidden_t", "child_t", "mixed_t"}
    flat = types["flat_t"]
    assert flat.module == "my_types" and flat.extends is None
    # Components only: the type-bound procedures are not.
    assert [(c.name, c.base, c.kind, c.rank, c.allocatable) for c in flat.components] == [
        ("n", "integer", None, 0, False), ("a", "real", "r8", 2, True),
        ("b", "real", "r8", 1, True), ("on", "logical", None, 1, False)]
    assert not types["hidden_t"].components[0].public
    assert types["child_t"].extends == "flat_t"
    assert types["mixed_t"].components[1].pointer
    # Type components are not module variables.
    module_scope = next(s for s in facts[1].scopes if s.name is None)
    assert "a" not in module_scope.variables and "n" not in module_scope.variables


def test_real_kinds_resolve_through_renames_and_constants(tmp_path):
    facts = _type_files(tmp_path)
    assert resolve_real_kind("r8", "my_types", facts) == "double"
    assert resolve_real_kind("sp", "my_types", facts) == "single"
    assert resolve_real_kind("unknown", "my_types", facts) is None
    assert resolve_real_kind("real64", None, facts) == "double"


def test_capture_layout_of_flat_types_and_why_not(tmp_path):
    facts = _type_files(tmp_path)
    layout, why = capture_layout("flat_t", facts)
    assert why == "" and layout.module == "my_types"
    assert layout.components == (("n", "integer", 0, False), ("a", "real", 2, True),
                                 ("b", "real", 1, True), ("on", "logical", 1, False))
    assert capture_layout("hidden_t", facts)[1] == "component x of type hidden_t is private"
    assert capture_layout("child_t", facts)[1] == "type child_t extends flat_t"
    assert capture_layout("mixed_t", facts)[1] == \
        "component s of type mixed_t has kind sp, not kind_phys"
    assert capture_layout("other_t", facts)[1] == \
        "no definition of type other_t in the scheme's sources"
