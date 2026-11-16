"""capture-shr-randnum: C sources in the capture test drivers' build.

A Fortran interface block with bind(c) procedures names C functions; the
capture closure adds the .c file under the source roots that defines each
one, and the directories of the quoted headers it includes, and the
generated CMake compiles them with C enabled (CESM share's shr_RandNum_mod
-> kissvec.c, dSFMT.c, dSFMT_utils.c for the RRTMGP McICA replays).
"""
import os

import pytest

from tests.unit.test_capture_cmake import _kessler_state_repo, _run_kessler_capture
from xdsl_ccpp.tools.capture_cmake import render_capture_cmakelists, render_capture_fragment
from xdsl_ccpp.transforms.fortran_preprocess import preprocess_fortran_source
from xdsl_ccpp.transforms.module_dependency_resolver import (
    _c_binding_label,
    scan_c_source,
    scan_fortran_source,
    source_closure,
)


def test_binding_label_from_name_or_procedure():
    assert _c_binding_label("subroutine kiss_rng(a, b) bind(c)") == "kiss_rng"
    assert _c_binding_label("  pure function F(x) result(y) bind(C, name='Get_Size')") == "Get_Size"
    assert _c_binding_label('subroutine s() bind ( c , name = "s_c" )') == "s_c"
    assert _c_binding_label("subroutine s(a)") is None


def test_fortran_scan_records_interface_c_bindings_only(tmp_path):
    src = tmp_path / "m.F90"
    src.write_text(
        "module m\n"
        "  interface\n"
        "    subroutine c_fill(n, x) bind(c, name='c_fill')\n"
        "      integer, value :: n\n"
        "    end subroutine c_fill\n"
        "  end interface\n"
        "contains\n"
        "  subroutine callable_from_c() bind(c)\n"
        "  end subroutine callable_from_c\n"
        "end module m\n")
    # A Fortran procedure with bind(c) is defined here, not needed from C.
    assert scan_fortran_source(str(src)).c_bindings == frozenset({"c_fill"})


def test_c_scan_finds_file_scope_definitions(tmp_path):
    src = tmp_path / "x.c"
    src.write_text(
        '#include <stdlib.h>\n'
        '#include "x.h"\n'
        '#if defined(__cplusplus)\n'
        'extern "C" {\n'
        '#endif\n'
        '/* void not_this(void) { } */\n'
        'static const char *s = "brace { and paren )";\n'
        'int proto(int a);\n'
        '#if defined(FAST)\n'
        '    static void twice(int n) {\n'
        '#else\n'
        '    static void twice(int n) {\n'
        '#endif\n'
        '        if (n) { n = 0; }\n'
        '    }\n'
        'void after(double *x,\n'
        '           int n) {\n'
        '    for (int i = 0; i < n; i++) { x[i] = 0.; }\n'
        '}\n'
        '#if defined(__cplusplus)\n'
        '}\n'
        '#endif\n')
    facts = scan_c_source(str(src))
    assert facts.functions == frozenset({"twice", "after"})
    assert facts.includes == ("x.h",)


def _c_tree(tmp_path):
    """root/src/rng_mod.F90 binds c_rng (root/src/rng.c, which includes
    rng.h from root/include) and c_seed (root/src/seed.c)."""
    root = tmp_path / "share"
    (root / "src").mkdir(parents=True)
    (root / "include").mkdir()
    (root / "src" / "rng_mod.F90").write_text(
        "module rng_mod\n"
        "  use, intrinsic :: iso_c_binding\n"
        "  interface\n"
        "    subroutine c_rng(n, x) bind(c)\n"
        "      import :: c_int, c_double\n"
        "      integer(c_int), value :: n\n"
        "      real(c_double) :: x(n)\n"
        "    end subroutine c_rng\n"
        "    subroutine c_seed(s) bind(c, name='c_seed')\n"
        "      import :: c_int\n"
        "      integer(c_int), value :: s\n"
        "    end subroutine c_seed\n"
        "  end interface\n"
        "end module rng_mod\n")
    (root / "src" / "rng.c").write_text(
        '#include "rng.h"\nvoid c_rng(int n, double *x) {\n  int i;\n'
        '  for (i = 0; i < n; i++) x[i] = RNG_HALF;\n}\n')
    (root / "src" / "seed.c").write_text("void c_seed(int s) {\n  (void) s;\n}\n")
    (root / "include" / "rng.h").write_text('#include "rng_params.h"\n')
    (root / "include" / "rng_params.h").write_text("#define RNG_HALF 0.5\n")
    return root


def test_closure_adds_bound_c_files_and_header_dirs(tmp_path):
    root = _c_tree(tmp_path)
    user = tmp_path / "user.F90"
    user.write_text("module user\n  use rng_mod\nend module user\n")
    closure = source_closure([str(user)], None, preproc_defs={},
                             extra_roots=[str(root / "src"), str(root / "include")])
    assert not closure.unresolved
    assert [os.path.basename(p) for p in closure.c_sources] == ["rng.c", "seed.c"]
    assert closure.include_dirs == [str(root / "include")]


def test_closure_reports_a_c_function_defined_nowhere(tmp_path):
    root = _c_tree(tmp_path)
    os.remove(root / "src" / "seed.c")
    closure = source_closure([str(root / "src" / "rng_mod.F90")], None, preproc_defs={},
                             extra_roots=[str(root / "src")])
    assert closure.unresolved == {
        "c_seed (C)": "bound in rng_mod.F90; defined in no .c file"}


def test_fragment_and_top_file_with_c():
    fragment = render_capture_fragment(
        "s", ["/a/s.F90", "/share/src/rng.c"], include_dirs=["/share/include"])
    assert '"/share/src/rng.c"' in fragment
    assert 'target_include_directories(test_s PRIVATE\n  "/share/include")' in fragment
    top = render_capture_cmakelists(["/a/ccpp_capture_mod.F90"], "/data", with_c=True)
    assert "enable_language(C)" in top
    assert "set(_cc_name nvc)" in top
    assert 'get_filename_component(_fc_dir "${CMAKE_Fortran_COMPILER}" DIRECTORY)' in top
    assert "${{" not in top  # no unformatted template braces
    # The model's per-file flags are Fortran flags.
    assert 'if(NOT _source MATCHES "[.][fF]90$")' in top
    assert "enable_language(C)" not in render_capture_cmakelists(
        ["/a/ccpp_capture_mod.F90"], "/data")


def test_driver_build_compiles_the_c_side_of_a_scheme_dependency(tmp_path):
    # kessler's module state comes from a module that calls C: the driver
    # build lists the C file and its header directory, and enables C.
    pytest.importorskip("fparser")
    scheme = _kessler_state_repo(tmp_path)
    root = _c_tree(tmp_path)
    state = scheme.parent / "utils" / "kessler_state.F90"
    state.write_text(state.read_text().replace(
        "  use ccpp_kinds, only: kind_phys\n",
        "  use ccpp_kinds, only: kind_phys\n  use rng_mod, only: c_rng\n", 1))
    drivers, _ = _run_kessler_capture(tmp_path, scheme, {
        "capture_scheme": ["kessler_update"],
        "capture_source_root": [str(root / "src"), str(root / "include")],
    })
    fragment = (drivers / "test_kessler_update.cmake").read_text()
    assert str(root / "src" / "rng.c") in fragment
    assert str(root / "src" / "seed.c") in fragment
    assert f'target_include_directories(test_kessler_update PRIVATE\n  "{root / "include"}")' in fragment
    assert "enable_language(C)" in (drivers / "CMakeLists.txt").read_text()


def test_if_not_defined_without_a_space():
    # "#if !defined(X)" (RandNum's dSFMT_interface.F90).
    source = "#if !defined(X)\nkeep\n#endif\n#if !defined(Y)\ndrop\n#endif\n"
    assert preprocess_fortran_source(source, "f.F90", {"Y": None}).split("\n")[:5] == [
        "", "keep", "", "", ""]
