"""The CMake build written next to the scheme I/O capture test drivers
(tools/capture_cmake.py, ccpp_dsl --capture-test-driver-dir), and
--capture-scheme's SCHEME[:PHASE] parsing."""

import os

import pytest

from xdsl.dialects import builtin

from xdsl_ccpp.frontend.ccpp_xml import ccppXML, parse_meta_file
from xdsl_ccpp.tools.capture_cmake import (
    kinds_sources,
    render_capture_cmakelists,
    render_capture_fragment,
    scheme_meta_files,
    scheme_source_root,
    support_sources,
)
from xdsl_ccpp.tools.ccpp_dsl import (
    _capture_entries,
    _capture_label,
    _capture_spec,
    ccppMain,
)
from xdsl_ccpp.util.errors import CcppInputError

K = "examples/kessler"


def test_fragment_builds_driver_and_scheme_sources_and_registers_the_test():
    text = render_capture_fragment("kessler", ["/src/kessler.F90", "/src/dep.F90"])
    assert "add_executable(test_kessler\n" in text
    assert "${CMAKE_CURRENT_LIST_DIR}/test_kessler.F90" in text
    assert '"/src/kessler.F90"' in text
    assert '"/src/dep.F90"' in text
    assert "target_link_libraries(test_kessler PRIVATE ccpp_capture_support)" in text
    assert ('add_test(NAME test_kessler COMMAND test_kessler '
            'WORKING_DIRECTORY "${CCPP_CAPTURE_DIR}")') in text
    # Each driver keeps its .mod files apart (schemes may share dependencies).
    assert "${CMAKE_BINARY_DIR}/mod/test_kessler" in text


def test_top_file_builds_support_library_and_includes_every_fragment():
    text = render_capture_cmakelists(support_sources("/out/ccpp_kinds.F90"), "/drivers/case.c01c")
    assert "add_library(ccpp_capture_support STATIC" in text
    for name in ("ccpp_kinds.F90", "ccpp_hashable.F90", "ccpp_hash_table.F90",
                 "ccpp_constituent_prop_mod.F90", "ccpp_scheme_utils.F90",
                 "ccpp_capture_mod.F90", "ccpp_capture_constituents_mod.F90",
                 "ccpp_capture_replay_mod.F90"):
        assert f'/{name}"' in text
    assert "find_program(NF_CONFIG nf-config REQUIRED)" in text
    # The tests run against the generating capture's directory unless
    # CCPP_CAPTURE_DIR overrides it (not cached, so a regeneration for
    # another capture moves an existing build along with it).
    assert 'set(CCPP_CAPTURE_DIR "" CACHE PATH' in text
    assert ('if(NOT CCPP_CAPTURE_DIR)\n'
            '  set(CCPP_CAPTURE_DIR "/drivers/case.c01c")\nendif()') in text
    assert "GLOB _entries" not in text
    assert "FATAL_ERROR" not in text
    assert "option(OPENACC" in text
    # nvfortran: no FMA (as CAM-SIMA builds), and a CPU build must not
    # compile the schemes' !$acc directives (nvfortran does by default).
    assert "add_compile_options(-Mnofma)" in text
    assert "list(APPEND _acc_flags -gpu=${CCPP_CAPTURE_GPU_TARGET},nofma,math_uniform)" in text
    assert 'set(CCPP_CAPTURE_GPU_TARGET "cc80" CACHE STRING' in text
    assert "add_compile_options(-noacc)" in text
    # As CIME compiles CAM-SIMA (coords_1d.F90's declarations use it).
    assert "add_compile_definitions(USE_CONTIGUOUS=)" in text
    # BLAS (PUMAS's neural net calls dgemm), optional: never a configure error.
    assert "find_package(BLAS QUIET)" in text
    assert "target_link_libraries(ccpp_capture_support PUBLIC ${BLAS_LIBRARIES})" in text
    assert 'file(GLOB _ccpp_capture_tests CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/test_*.cmake")' in text
    assert "enable_testing()" in text


def test_scheme_sources_are_relative_to_a_selectable_root():
    text = render_capture_fragment(
        "kessler", ["/fork/schemes/kessler/kessler.F90", "/elsewhere/dep.F90"], "/fork")
    assert '  "${CCPP_CAPTURE_SCHEME_ROOT}/schemes/kessler/kessler.F90"' in text
    # A source outside the root keeps its absolute path.
    assert '  "/elsewhere/dep.F90"' in text
    top = render_capture_cmakelists(support_sources("/out/ccpp_kinds.F90"), "/d", "/fork")
    assert 'set(_ccpp_capture_scheme_root "$ENV{CCPP_CAPTURE_SCHEME_ROOT}")' in top
    assert 'set(_ccpp_capture_scheme_root "/fork")' in top
    assert 'set(CCPP_CAPTURE_SCHEME_ROOT "${_ccpp_capture_scheme_root}" CACHE PATH' in top
    assert top.index("CCPP_CAPTURE_SCHEME_ROOT") < top.index("include(${_test})")


def test_fragment_builds_one_version_of_each_cpu_gpu_variant():
    text = render_capture_fragment(
        "rrtmgp_lw_rte", ["/fork/schemes/rrtmgp_lw_rte.F90"], "/fork",
        [("/fork/k/mo_k.F90", "/fork/k/accel/mo_k.F90")])
    assert ("if(OPENACC)\n"
            "  target_sources(test_rrtmgp_lw_rte PRIVATE\n"
            '  "${CCPP_CAPTURE_SCHEME_ROOT}/k/accel/mo_k.F90")\n'
            "else()\n"
            "  target_sources(test_rrtmgp_lw_rte PRIVATE\n"
            '  "${CCPP_CAPTURE_SCHEME_ROOT}/k/mo_k.F90")\n'
            "endif()\n") in text
    add_executable = text[:text.index("set_target_properties")]
    assert "mo_k.F90" not in add_executable
    assert "if(OPENACC)" not in render_capture_fragment("kessler", ["/src/kessler.F90"])


def test_scheme_source_root_is_the_nearest_git_checkout(tmp_path):
    repo = tmp_path / "atmospheric_physics"
    (repo / "schemes" / "kessler").mkdir(parents=True)
    (repo / ".git").write_text("gitdir: ../.git/modules/x\n")  # a submodule
    src = repo / "schemes" / "kessler" / "kessler.F90"
    src.write_text("")
    assert scheme_source_root(str(src)) == str(repo)


def test_share_stubs_are_in_the_support_library_and_provided():
    from xdsl_ccpp.tools.capture_cmake import capture_provided_modules

    support = support_sources("/out/ccpp_kinds.F90")
    stubs = [p for p in support if os.sep + "capture_stubs" + os.sep in p]
    assert [os.path.basename(p) for p in stubs] == ["shr_log_mod.F90", "shr_sys_mod.F90"]
    provided = capture_provided_modules(support)
    assert {"shr_log_mod", "shr_sys_mod"} <= provided
    # Only the capture build has them: a model build gets the real ones.
    from xdsl_ccpp.tools.ccpp_datatable import _resolve_framework_f90_files
    assert not any("capture_stubs" in p for p in _resolve_framework_f90_files())


def test_support_sources_exist():
    for path in support_sources("/out/ccpp_kinds.F90")[1:]:
        assert os.path.isfile(path), path


def test_scheme_meta_files_maps_scheme_tables_only(tmp_path):
    scheme = tmp_path / "physics.meta"
    scheme.write_text(
        "[ccpp-table-properties]\n  name = alpha\n  type = scheme\n"
        "[ccpp-arg-table]\n  name = alpha_run\n  type = scheme\n"
        "[ccpp-table-properties]\n  name = beta  # second scheme in one file\n  type = scheme\n"
    )
    host = tmp_path / "host.meta"
    host.write_text("[ccpp-table-properties]\n  name = host_mod\n  type = module\n")
    assert scheme_meta_files([str(scheme), str(host)]) == {
        "alpha": str(scheme), "beta": str(scheme),
    }


def test_ccpp_dsl_writes_a_fragment_per_captured_scheme(tmp_path):
    tool = ccppMain()
    options_db = tool.default_options_db()
    drivers = tmp_path / "drivers"
    options_db.update({
        "host_files": [f"{K}/host_ftn/kessler_host_mod.meta", f"{K}/host_ftn/kessler_host_sub.meta"],
        "scheme_files": [f"{K}/scheme/kessler.meta", f"{K}/scheme/kessler_update.meta"],
        "suites": [f"{K}/scheme/kessler_suite.xml"],
        "capture_scheme": ["kessler", "kessler_update:run"],
        "capture_test_driver_dir": str(drivers),
        "out": str(tmp_path / "out"), "tempdir": str(tmp_path / "tmp"), "verbose": 0,
    })
    tool.run(options_db)

    assert sorted(os.listdir(drivers)) == [
        "CMakeLists.txt", "test_kessler.F90", "test_kessler.cmake",
        "test_kessler_update.F90", "test_kessler_update.cmake",
    ]
    fragment = (drivers / "test_kessler.cmake").read_text()
    # Relative to the checkout holding the scheme (here xdsl-ccpp itself).
    assert f'"${{CCPP_CAPTURE_SCHEME_ROOT}}/{K}/scheme/kessler.F90"' in fragment
    top = (drivers / "CMakeLists.txt").read_text()
    assert f'set(_ccpp_capture_scheme_root "{os.path.abspath(".")}")' in top
    assert str(tmp_path / "out" / "ccpp_kinds.F90") in top
    assert f'set(CCPP_CAPTURE_DIR "{drivers}")' in top  # no label: the driver dir
    # Two capture-pass instances share one set of declarations in the cap.
    cap = (tmp_path / "out" / "kessler_suite_cap.F90").read_text()
    assert cap.count("use ccpp_capture_mod, only: ccpp_capture_begin\n") == 1


@pytest.mark.parametrize("spec, expected", [
    ("kessler", ("kessler", "")),
    ("kessler:run", ("kessler", "run")),
    ("kessler:initialize", ("kessler", "initialize")),
    (" kessler : timestep_final ", ("kessler", "timestep_final")),
    ("qneg:initialize,run", ("qneg", "initialize,run")),
    ("qneg: initialize , run,initialize", ("qneg", "initialize,run")),
])
def test_capture_spec_phase(spec, expected):
    assert _capture_spec(spec) == expected


@pytest.mark.parametrize("label", ["case.c01b", " SMS_Ln2.ne3pg3.c01b "])
def test_capture_label_accepts_a_directory_name(label):
    assert _capture_label(label) == label.strip()


@pytest.mark.parametrize("label", ["", ".", "..", "a/b", 'a"b', "a\\b"])
def test_capture_label_rejects_anything_but_one_directory_name(label):
    with pytest.raises(CcppInputError):
        _capture_label(label)


def test_ccpp_dsl_label_names_the_data_subdirectory(tmp_path):
    tool = ccppMain()
    options_db = tool.default_options_db()
    drivers = tmp_path / "drivers"
    options_db.update({
        "host_files": [f"{K}/host_ftn/kessler_host_mod.meta", f"{K}/host_ftn/kessler_host_sub.meta"],
        "scheme_files": [f"{K}/scheme/kessler.meta", f"{K}/scheme/kessler_update.meta"],
        "suites": [f"{K}/scheme/kessler_suite.xml"],
        "capture_scheme": ["kessler"],
        "capture_test_driver_dir": str(drivers),
        "capture_label": "case.c01b",
        "out": str(tmp_path / "out"), "tempdir": str(tmp_path / "tmp"), "verbose": 0,
    })
    tool.run(options_db)

    assert (drivers / "case.c01b").is_dir()  # created for the run to write into
    cap = (tmp_path / "out" / "kessler_suite_cap.F90").read_text()
    # The caps name the driver dir; the runtime appends the label.
    assert f"'{drivers}')" in cap
    assert "call ccpp_capture_set_info('case.c01b', 'xdsl_ccpp " in cap
    # The build tests this capture only.
    top = (drivers / "CMakeLists.txt").read_text()
    assert f'set(CCPP_CAPTURE_DIR "{drivers / "case.c01b"}")' in top


@pytest.mark.parametrize("spec", ["kessler:init", "kessler:all", ":run"])
def test_capture_spec_rejects_unknown_phase_or_missing_scheme(spec):
    # A table suffix such as `init` used to capture nothing, silently.
    with pytest.raises(CcppInputError):
        _capture_spec(spec)


_KESSLER_METAS = [f"{K}/scheme/kessler.meta", f"{K}/scheme/kessler_update.meta"]


def test_capture_entries_reads_a_scheme_list_file(tmp_path):
    listing = tmp_path / "schemes.txt"
    listing.write_text(
        "# schemes to capture\n"
        "kessler\n"
        "\n"
        "  kessler_update:run   # one phase\n"
    )
    assert _capture_entries([str(listing)], _KESSLER_METAS) == ["kessler", "kessler_update:run"]


def test_capture_entries_mixes_names_and_files(tmp_path):
    listing = tmp_path / "schemes.txt"
    listing.write_text("kessler_update\n")
    assert _capture_entries(["kessler:run", str(listing)], _KESSLER_METAS) == [
        "kessler:run", "kessler_update",
    ]


def test_capture_entries_unknown_scheme_names_the_file_and_line(tmp_path):
    listing = tmp_path / "schemes.txt"
    listing.write_text("kessler\nno_such_scheme\n")
    with pytest.raises(CcppInputError, match=rf"{listing}:2: 'no_such_scheme' is neither"):
        _capture_entries([str(listing)], _KESSLER_METAS)


def test_capture_entries_unknown_name_or_missing_file():
    with pytest.raises(CcppInputError, match="neither a file nor a scheme"):
        _capture_entries(["schemes.txt"], _KESSLER_METAS)


def test_capture_entries_bad_phase_names_the_line(tmp_path):
    listing = tmp_path / "schemes.txt"
    listing.write_text("kessler:running\n")
    with pytest.raises(CcppInputError, match=rf"{listing}:1: .*unknown phase 'running'"):
        _capture_entries([str(listing)], _KESSLER_METAS)


def test_capture_entries_rejects_a_scheme_listed_twice(tmp_path):
    listing = tmp_path / "schemes.txt"
    listing.write_text("kessler\n")
    with pytest.raises(CcppInputError, match="'kessler' is already captured"):
        _capture_entries([str(listing), "kessler:run"], _KESSLER_METAS)


def test_ccpp_dsl_captures_every_scheme_of_a_list_file(tmp_path):
    listing = tmp_path / "schemes.txt"
    listing.write_text("kessler\nkessler_update:run\n")
    tool = ccppMain()
    options_db = tool.default_options_db()
    drivers = tmp_path / "drivers"
    options_db.update({
        "host_files": [f"{K}/host_ftn/kessler_host_mod.meta", f"{K}/host_ftn/kessler_host_sub.meta"],
        "scheme_files": _KESSLER_METAS,
        "suites": [f"{K}/scheme/kessler_suite.xml"],
        "capture_scheme": [str(listing)],
        "capture_test_driver_dir": str(drivers),
        "out": str(tmp_path / "out"), "tempdir": str(tmp_path / "tmp"), "verbose": 0,
    })
    tool.run(options_db)

    assert sorted(os.listdir(drivers)) == [
        "CMakeLists.txt", "test_kessler.F90", "test_kessler.cmake",
        "test_kessler_update.F90", "test_kessler_update.cmake",
    ]


def test_capture_spec_rejects_an_unknown_phase_in_a_list():
    with pytest.raises(CcppInputError, match="unknown phase 'final'"):
        _capture_spec("qneg:initialize,final")


def test_ccpp_dsl_captures_only_the_listed_phases(tmp_path):
    tool = ccppMain()
    options_db = tool.default_options_db()
    drivers = tmp_path / "drivers"
    options_db.update({
        "host_files": [f"{K}/host_ftn/kessler_host_mod.meta", f"{K}/host_ftn/kessler_host_sub.meta"],
        "scheme_files": _KESSLER_METAS,
        "suites": [f"{K}/scheme/kessler_suite.xml"],
        "capture_scheme": ["kessler:run,finalize"],
        "capture_test_driver_dir": str(drivers),
        "out": str(tmp_path / "out"), "tempdir": str(tmp_path / "tmp"), "verbose": 0,
    })
    tool.run(options_db)
    cap = (tmp_path / "out" / "kessler_suite_cap.F90").read_text()
    # kessler has init and run phases: init is not in the list.
    assert "call ccpp_capture_begin('kessler_run', 'before')" in cap
    assert "ccpp_capture_begin('kessler_init'" not in cap
    driver = (drivers / "test_kessler.F90").read_text()
    assert "! -- kessler_run --" in driver
    assert "! -- kessler_init --" not in driver


def _kessler_without_memory_space(tmp_path):
    """examples/kessler's schemes with their memory_space lines removed,
    as CAM-SIMA's are now: the device residency is only in the .F90's
    own OpenACC (present clauses)."""
    import shutil

    scheme = tmp_path / "scheme"
    shutil.copytree(f"{K}/scheme", scheme)
    for meta in scheme.glob("*.meta"):
        lines = meta.read_text().splitlines(keepends=True)
        meta.write_text("".join(l for l in lines if "memory_space" not in l))
    return scheme


def _run_kessler_capture(tmp_path, scheme, extra=None):
    tool = ccppMain()
    options_db = tool.default_options_db()
    drivers = tmp_path / "drivers"
    options_db.update({
        "host_files": [f"{K}/host_ftn/kessler_host_mod.meta", f"{K}/host_ftn/kessler_host_sub.meta"],
        "scheme_files": [str(scheme / "kessler.meta"), str(scheme / "kessler_update.meta")],
        "suites": [str(scheme / "kessler_suite.xml")],
        "capture_scheme": ["kessler", "kessler_update"],
        "capture_test_driver_dir": str(drivers),
        "out": str(tmp_path / "out"), "tempdir": str(tmp_path / "tmp"), "verbose": 0,
    })
    options_db.update(extra or {})
    tool.run(options_db)
    return drivers, (tmp_path / "out" / "kessler_suite_cap.F90").read_text()


def test_cpu_capture_drivers_get_device_data_from_the_source(tmp_path):
    # No --directive and no memory_space in .meta: the drivers still put
    # what the schemes' present clauses need on the device, so the CPU
    # capture replays on a GPU.
    pytest.importorskip("fparser")
    drivers, cap = _run_kessler_capture(tmp_path, _kessler_without_memory_space(tmp_path))
    update = (drivers / "test_kessler_update.F90").read_text()
    enter = " ".join(l for l in update.splitlines() if "!$acc enter data" in l)
    assert "theta" in enter and "exner" in enter, enter
    assert "!$acc exit data" in update
    assert "!$acc enter data" in (drivers / "test_kessler.F90").read_text()
    # The caps are a CPU generation's: no directives at all.
    assert "!$acc" not in cap and "!$omp" not in cap


def test_cpu_capture_caps_unchanged_by_driver_device_data(tmp_path):
    # The driver-only device list must not reach the cap: same cap as a
    # generation that captures nothing of the device data (fparser absent
    # would give it too) -- compare against a capture with the option
    # forced empty.
    pytest.importorskip("fparser")
    scheme = _kessler_without_memory_space(tmp_path)
    _, cap = _run_kessler_capture(tmp_path / "a", scheme)
    from unittest import mock

    with mock.patch.object(ccppMain, "_capture_driver_device_args",
                           lambda self, handle: setattr(self, "_capture_device_args", {})):
        drivers_b, cap_b = _run_kessler_capture(tmp_path / "b", scheme)
    assert cap == cap_b.replace(str(tmp_path / "b" / "drivers"), str(tmp_path / "a" / "drivers"))
    assert "!$acc enter data" not in (drivers_b / "test_kessler_update.F90").read_text()


def _meta_module(meta_files) -> builtin.ModuleOp:
    """The frontend IR of real .meta files on disk (dependencies_path
    resolved against each file's directory, as ccpp_dsl does)."""
    frontend = ccppXML()
    ops = [
        frontend.build_meta_ir(m, meta_file_path=str(path))
        for path in meta_files
        for m in parse_meta_file(str(path), True)
    ]
    return builtin.ModuleOp(ops)


def _kind_scheme_meta(path, name, kind_spec, deps, deps_path=None):
    lines = ["[ccpp-table-properties]", f"  name = {name}", "  type = scheme"]
    if kind_spec:
        lines.append(f"  kind_spec = {kind_spec}")
    lines += [f"  dependencies = {d}" for d in deps]
    if deps_path:
        lines.append(f"  dependencies_path = {deps_path}")
    lines += ["[ccpp-arg-table]", f"  name = {name}_run", "  type = scheme", ""]
    path.write_text("\n".join(lines))
    return path


def test_kinds_sources_finds_the_kind_spec_modules_dependency(tmp_path):
    """scheme-io-capture-kinds-deps: CAM-SIMA's pumas schemes declare
    kind_spec = pumas_kinds:pumas_r8=>kind_r8 with pumas/pumas_kinds.F90 in
    their dependencies; the generated ccpp_kinds.F90 then uses pumas_kinds,
    so its source belongs in the support library."""
    (tmp_path / "pumas").mkdir()
    kinds = tmp_path / "pumas" / "pumas_kinds.F90"
    kinds.write_text("module pumas_kinds\nend module pumas_kinds\n")
    (tmp_path / "pumas" / "micro_pumas_utils.F90").write_text("module micro_pumas_utils\nend module\n")
    spec = "pumas_kinds:pumas_r8=>kind_r8"
    module = _meta_module([
        _kind_scheme_meta(tmp_path / "post.meta", "pumas_post_main", spec,
                          ["pumas/micro_pumas_utils.F90", "pumas/pumas_kinds.F90"]),
        _kind_scheme_meta(tmp_path / "pre.meta", "dims_pre", spec, ["pumas/pumas_kinds.F90"]),
        _kind_scheme_meta(tmp_path / "plain.meta", "plain", None, ["pumas/micro_pumas_utils.F90"]),
    ])
    sources, missing = kinds_sources(module)
    assert [os.path.realpath(p) for p in sources] == [os.path.realpath(kinds)]
    assert missing == []


def test_kinds_sources_falls_back_to_the_file_declaring_the_module(tmp_path):
    (tmp_path / "adjust").mkdir()
    src = tmp_path / "adjust" / "all_kinds.F90"
    src.write_text("! kinds\n  MODULE temp_kinds  ! precision\nend module temp_kinds\n")
    module = _meta_module([_kind_scheme_meta(
        tmp_path / "t.meta", "temp_adjust", "temp_kinds:kind_temp=>temp_r8",
        ["all_kinds.F90"], "adjust")])
    sources, missing = kinds_sources(module)
    assert [os.path.realpath(p) for p in sources] == [os.path.realpath(src)]
    assert missing == []


def test_kinds_sources_reports_a_kind_module_no_dependency_provides(tmp_path):
    module = _meta_module([_kind_scheme_meta(
        tmp_path / "t.meta", "temp_adjust", "temp_kinds:kind_temp=>temp_r8", [])])
    assert kinds_sources(module) == ([], ["temp_kinds"])


def test_kind_module_sources_come_before_ccpp_kinds_in_the_support_library():
    text = render_capture_cmakelists(
        support_sources("/out/ccpp_kinds.F90", ["/phys/pumas/pumas_kinds.F90"]), "/d")
    assert '"/phys/pumas/pumas_kinds.F90"' in text
    assert (text.index('"/phys/pumas/pumas_kinds.F90"')
            < text.index('"/out/ccpp_kinds.F90"')
            < text.index("ccpp_capture_mod.F90"))


def _kessler_with_mpi(tmp_path, module_level: bool):
    """examples/kessler's schemes, kessler_update.F90 using MPI: in its
    module's specification part (*module_level*), else only in a
    subroutine its timestep_final phase calls (as qneg does)."""
    scheme = _kessler_without_memory_space(tmp_path)
    path = scheme / "kessler_update.F90"
    source = path.read_text()
    if module_level:
        marker = "   use ccpp_kinds, only: kind_phys\n"
        assert marker in source
        source = source.replace(marker, marker + "   include 'mpif.h'\n", 1)
    else:
        marker = "   end subroutine kessler_update_timestep_final\n"
        assert marker in source
        source = source.replace(marker, "      call update_summary()\n" + marker, 1)
        source = source.replace(
            "end module kessler_update",
            "   subroutine update_summary()\n      use mpi, only: mpi_sum\n"
            "   end subroutine update_summary\nend module kessler_update", 1)
    path.write_text(source)
    return scheme


def test_phases_reaching_mpi_are_not_captured(tmp_path):
    # scheme-io-capture-host-module-schemes: a replay runs as one serial
    # process, so a phase whose entry point reaches MPI is not captured;
    # the scheme's other phases are, and a report says why.
    scheme = _kessler_with_mpi(tmp_path, module_level=False)
    drivers, cap = _run_kessler_capture(tmp_path, scheme)

    assert "ccpp_capture_begin('kessler_update_run'" in cap
    assert "ccpp_capture_begin('kessler_update_timestep_final'" not in cap
    assert (drivers / "test_kessler_update.F90").exists()
    report = (drivers / "test_kessler_update.skipped").read_text()
    assert ("kessler_update: phase timestep_final not captured: "
            "kessler_update_timestep_final calls update_summary, which has use mpi "
            "(kessler_update.F90); a replay runs as one serial process") in report


def test_listed_phases_not_reaching_mpi_are_captured_as_before(tmp_path):
    scheme = _kessler_with_mpi(tmp_path, module_level=False)
    drivers, cap = _run_kessler_capture(
        tmp_path, scheme, {"capture_scheme": ["kessler", "kessler_update:initialize,run"]})
    assert "ccpp_capture_begin('kessler_update_run'" in cap
    assert not (drivers / "test_kessler_update.skipped").exists()


def test_a_scheme_using_mpi_in_every_phase_is_not_captured(tmp_path):
    # MPI in the module's specification part reaches every phase: no
    # capture calls and no driver, and an earlier generation's driver and
    # fragment are removed. The other scheme is unaffected.
    scheme = _kessler_with_mpi(tmp_path, module_level=True)
    drivers = tmp_path / "drivers"
    drivers.mkdir()
    (drivers / "test_kessler_update.F90").write_text("stale\n")
    (drivers / "test_kessler_update.cmake").write_text("stale\n")

    drivers, cap = _run_kessler_capture(tmp_path, scheme)

    assert "ccpp_capture_begin('kessler_update_" not in cap
    assert "ccpp_capture_begin('kessler_run'" in cap
    assert sorted(os.listdir(drivers)) == [
        "CMakeLists.txt", "test_kessler.F90", "test_kessler.cmake",
        "test_kessler_update.skipped",
    ]
    report = (drivers / "test_kessler_update.skipped").read_text()
    assert ("kessler_update: not captured: kessler_update_init is in module "
            "kessler_update, which has include 'mpif.h' (kessler_update.F90)") in report


def _kessler_repo(tmp_path, kessler_use: str, update_use: str):
    """examples/kessler's schemes in a repository of their own (a .git
    marks its root) with a utility module, kessler.F90 and
    kessler_update.F90 each given one more USE statement."""
    repo = tmp_path / "repo"
    scheme = _kessler_without_memory_space(repo)
    (repo / ".git").mkdir()
    (repo / "utils").mkdir()
    (repo / "utils" / "kessler_util.F90").write_text(
        "module kessler_util\n  use shared_consts\nend module kessler_util\n")
    (repo / "utils" / "consts.F90").write_text(
        "module shared_consts\n  use ccpp_kinds\n  use netcdf\nend module shared_consts\n")
    for name, use in (("kessler.F90", kessler_use), ("kessler_update.F90", update_use)):
        source = (scheme / name).read_text()
        first_use = "   use ccpp_kinds, only:"
        assert first_use in source
        (scheme / name).write_text(source.replace(first_use, f"   use {use}\n{first_use}", 1))
    return scheme


def test_driver_builds_with_the_repository_modules_the_scheme_uses(tmp_path):
    # scheme-io-capture-host-module-schemes B: kessler_util and, through it,
    # shared_consts (in a file not named after it) join the fragment;
    # ccpp_kinds and netcdf come from the build.
    scheme = _kessler_repo(tmp_path, "kessler_util", "ccpp_kinds")
    drivers, _ = _run_kessler_capture(tmp_path, scheme)
    fragment = (drivers / "test_kessler.cmake").read_text()
    assert '"${CCPP_CAPTURE_SCHEME_ROOT}/scheme/kessler.F90"' in fragment
    assert '"${CCPP_CAPTURE_SCHEME_ROOT}/utils/kessler_util.F90"' in fragment
    assert '"${CCPP_CAPTURE_SCHEME_ROOT}/utils/consts.F90"' in fragment
    update = (drivers / "test_kessler_update.cmake").read_text()
    assert "utils/" not in update
    assert not (drivers / "test_kessler.skipped").exists()


def test_driver_builds_with_share_code_from_a_source_root(tmp_path):
    # scheme-io-capture-share-code: a module not in the repository is taken
    # from --capture-source-root (absolute path in the fragment); the
    # share modules that need ESMF are the support library's stubs.
    share = tmp_path / "share" / "src"
    share.mkdir(parents=True)
    (share / "shr_kind_mod.F90").write_text("module shr_kind_mod\nend module shr_kind_mod\n")
    (share / "shr_sys_mod.F90").write_text("module shr_sys_mod\n  use esmf\nend module\n")
    scheme = _kessler_repo(tmp_path, "kessler_util", "ccpp_kinds")
    (scheme.parent / "utils" / "kessler_util.F90").write_text(
        "module kessler_util\n  use shared_consts\n  use shr_kind_mod\n"
        "  use shr_sys_mod, only: shr_sys_abort\nend module kessler_util\n")
    drivers, _ = _run_kessler_capture(tmp_path, scheme,
                                      {"capture_source_root": [str(share)]})
    fragment = (drivers / "test_kessler.cmake").read_text()
    assert f'"{share}/shr_kind_mod.F90"' in fragment
    assert "shr_sys_mod.F90" not in fragment
    assert not (drivers / "test_kessler.skipped").exists()
    top = (drivers / "CMakeLists.txt").read_text()
    assert "capture_stubs/shr_sys_mod.F90" in top


def _kessler_state_repo(tmp_path):
    """kessler_init sets module variable kstate (module kessler_state),
    which kessler_update_run reads (scheme-io-capture-module-state-setup)."""
    scheme = _kessler_repo(tmp_path, "kessler_state, only: kstate",
                           "kessler_state, only: kstate")
    (scheme.parent / "utils" / "kessler_state.F90").write_text(
        "module kessler_state\n  use ccpp_kinds, only: kind_phys\n"
        "  real(kind_phys) :: kstate = 0.\nend module kessler_state\n")
    kessler = scheme / "kessler.F90"
    head, tail = kessler.read_text().split("subroutine kessler_init", 1)
    kessler.write_text(head + "subroutine kessler_init"
                       + tail.replace("      errflg = 0\n", "      errflg = 0\n      kstate = 2.\n", 1))
    update = scheme / "kessler_update.F90"
    head, tail = update.read_text().split("subroutine kessler_update_run", 1)
    update.write_text(head + "subroutine kessler_update_run" + tail.replace(
        "      errflg = 0\n", "      errflg = 0\n      if (kstate < 0.) errflg = 1\n", 1))
    return scheme


def test_driver_replays_the_init_that_sets_module_state_first(tmp_path):
    # kessler_update_run reads kstate, which kessler_init sets: the
    # kessler_update driver replays kessler_init's captured call first (not
    # compared), and its fragment builds kessler.F90. kessler_update's own
    # init sets its gravit, which its driver replays anyway: nothing more.
    pytest.importorskip("fparser")
    drivers, _ = _run_kessler_capture(tmp_path, _kessler_state_repo(tmp_path))
    driver = (drivers / "test_kessler_update.F90").read_text()
    setup = driver.index("-- setup: kessler_init (sets module state the replay reads; not compared) --")
    assert setup < driver.index("-- kessler_update_init --")
    assert "call kessler_init(" in driver
    assert "setup1_" in driver  # its arguments are apart from kessler_update's
    assert "use kessler, only: kessler_init" in driver
    assert "scheme/kessler.F90" in (drivers / "test_kessler_update.cmake").read_text()
    assert not (drivers / "test_kessler_update.skipped").exists()
    assert "-- setup:" not in (drivers / "test_kessler.F90").read_text()


def test_unlisted_setter_is_captured_for_the_drivers_only(tmp_path):
    # kessler is not on the capture list: its init is captured anyway, for
    # kessler_update's driver, but it gets no driver of its own.
    pytest.importorskip("fparser")
    drivers, cap = _run_kessler_capture(tmp_path, _kessler_state_repo(tmp_path),
                                        {"capture_scheme": ["kessler_update"]})
    assert "ccpp_capture_begin('kessler_init'" in cap
    assert "ccpp_capture_begin('kessler_run'" not in cap
    assert not (drivers / "test_kessler.F90").exists()
    assert not (drivers / "test_kessler.cmake").exists()
    assert "-- setup: kessler_init" in (drivers / "test_kessler_update.F90").read_text()


def test_setter_that_cannot_be_replayed_is_reported(tmp_path):
    # kessler_init also reaches MPI: not captured (a replay is serial), so
    # kessler_update's driver gets no setup and the report says why.
    pytest.importorskip("fparser")
    scheme = _kessler_state_repo(tmp_path)
    (scheme.parent / "utils" / "kessler_state.F90").write_text(
        "module kessler_state\n  use ccpp_kinds, only: kind_phys\n"
        "  real(kind_phys) :: kstate = 0.\ncontains\n  subroutine sync_state()\n"
        "    use mpi\n  end subroutine sync_state\nend module kessler_state\n")
    kessler = scheme / "kessler.F90"
    kessler.write_text(kessler.read_text()
                       .replace("kessler_state, only: kstate", "kessler_state, only: kstate, sync_state")
                       .replace("      kstate = 2.\n", "      kstate = 2.\n      call sync_state()\n"))
    drivers, _ = _run_kessler_capture(tmp_path, scheme)
    assert "-- setup:" not in (drivers / "test_kessler_update.F90").read_text()
    report = (drivers / "test_kessler_update.skipped").read_text()
    assert ("kessler_update_run reads module variables kstate (kessler_state), set by "
            "kessler_init (scheme kessler, initialize phase), which the replay does not "
            "run (kessler_init calls sync_state, which has use mpi (kessler_state.F90))") \
        in report


def test_driver_needing_a_host_module_is_not_built(tmp_path):
    # scheme-io-capture-host-module-schemes A: a module found neither in
    # the repository nor in the support library gets the driver no
    # fragment (an earlier one is removed) and a report; the capture
    # stays, and the other scheme's driver builds.
    scheme = _kessler_repo(tmp_path, "kessler_util", "cam_history, only: history_out_field")
    drivers = tmp_path / "drivers"
    drivers.mkdir()
    (drivers / "test_kessler_update.cmake").write_text("stale\n")
    drivers, cap = _run_kessler_capture(tmp_path, scheme)

    assert "ccpp_capture_begin('kessler_update_run'" in cap
    assert (drivers / "test_kessler_update.F90").exists()
    assert not (drivers / "test_kessler_update.cmake").exists()
    assert (drivers / "test_kessler.cmake").exists()
    report = (drivers / "test_kessler_update.skipped").read_text()
    assert ("kessler_update: test_kessler_update.F90 is not built: it needs modules "
            "the capture build cannot supply (searched: the scheme's repository, any "
            "--capture-source-root, the capture support library): cam_history "
            "(used by kessler_update.F90)") in report


# scheme-io-capture-ddt-args: derived types recorded component by component.

def _run_ddthost_capture(tmp_path, flat: bool):
    """examples/ddthost in a repository of its own, make_ddt captured;
    *flat*: its vmr_type without the nested derived-type components."""
    import shutil

    repo = tmp_path / "ddthost"
    shutil.copytree("examples/ddthost", repo)
    (repo / ".git").mkdir()
    if flat:
        source = repo / "scheme" / "make_ddt.F90"
        source.write_text(source.read_text()
                          .replace("      type(ty_ddt2) :: error_maybe\n", "")
                          .replace("      type(ty_ddt3) :: burma_shave\n", ""))
    tool = ccppMain()
    options_db = tool.default_options_db()
    scheme_dir = repo / "scheme"
    options_db.update({
        "host_files": [str(scheme_dir / "host_ccpp_ddt.meta")] + [
            str(repo / "host_ftn" / f"{name}.meta")
            for name in ("test_host_data", "test_host_mod", "test_host")],
        "scheme_files": [str(scheme_dir / f"{name}.meta") for name in (
            "make_ddt", "environ_conditions", "setup_coeffs", "temp_set",
            "temp_calc_adjust", "temp_adjust")],
        "suites": [str(scheme_dir / "ddt_suite.xml"), str(scheme_dir / "temp_suite.xml")],
        "capture_scheme": ["make_ddt"],
        "capture_test_driver_dir": str(tmp_path / "drivers"),
        "out": str(tmp_path / "out"), "tempdir": str(tmp_path / "tmp"), "verbose": 0,
    })
    tool.run(options_db)
    return tmp_path / "drivers", (tmp_path / "out" / "ddt_suite_cap.F90").read_text()


def test_flat_derived_type_is_captured_and_replayed_by_component(tmp_path):
    pytest.importorskip("fparser")
    drivers, cap = _run_ddthost_capture(tmp_path, flat=True)
    # The cap writes vmr's components in sub-group vmr, an allocatable one
    # only when allocated.
    block = cap[cap.index("call ccpp_capture_begin_ddt('vmr')"):]
    block = block[:block.index("call ccpp_capture_end_ddt()")]
    assert "call ccpp_capture('nvmr', vmr%nvmr," in block
    assert "if (allocated(vmr%vmr_array)) then" in block
    driver = (drivers / "test_make_ddt.F90").read_text()
    assert "type(vmr_type) :: vmr" in driver
    assert "call ccpp_capture_read('in/vmr', 'nvmr', vmr%nvmr)" in driver
    assert "call ccpp_capture_read('out/vmr', 'nvmr', vmr_expected%nvmr)" in driver
    assert "-- make_ddt_run --" in driver
    # ccpp_info_t has a character component: its phase is left out, and why.
    report = (drivers / "test_make_ddt.skipped").read_text()
    assert "derived type ccpp_info_t is not recorded: component errmsg of type " \
        "ccpp_info_t is character" in report


def test_nested_derived_type_is_reported(tmp_path):
    pytest.importorskip("fparser")
    drivers, cap = _run_ddthost_capture(tmp_path, flat=False)
    assert "ccpp_capture_begin_ddt('vmr')" not in cap
    report = (drivers / "test_make_ddt.skipped").read_text()
    assert "make_ddt_run: argument 'vmr' is of derived type vmr_type" in report
    assert "derived type vmr_type is not recorded: component error_maybe of type " \
        "vmr_type is ty_ddt2" in report
