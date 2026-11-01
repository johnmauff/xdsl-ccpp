"""The CMake build written next to the scheme I/O capture test drivers
(tools/capture_cmake.py, ccpp_dsl --capture-test-driver-dir), and
--capture-scheme's SCHEME[:PHASE] parsing."""

import os

import pytest

from xdsl_ccpp.tools.capture_cmake import (
    render_capture_cmakelists,
    render_capture_fragment,
    scheme_meta_files,
    support_sources,
)
from xdsl_ccpp.tools.ccpp_dsl import _capture_label, _capture_spec, ccppMain
from xdsl_ccpp.util.errors import CcppInputError

K = "examples/kessler"


def test_fragment_builds_driver_and_scheme_sources_and_registers_the_test():
    text = render_capture_fragment("kessler", ["/src/kessler.F90", "/src/dep.F90"])
    assert "add_executable(test_kessler\n" in text
    assert "${CMAKE_CURRENT_LIST_DIR}/test_kessler.F90" in text
    assert '"/src/kessler.F90"' in text
    assert '"/src/dep.F90"' in text
    assert "target_link_libraries(test_kessler PRIVATE ccpp_capture_support)" in text
    assert "ccpp_capture_add_tests(test_kessler kessler)" in text
    # Each driver keeps its .mod files apart (schemes may share dependencies).
    assert "${CMAKE_BINARY_DIR}/mod/test_kessler" in text


def test_top_file_builds_support_library_and_includes_every_fragment():
    text = render_capture_cmakelists(support_sources("/out/ccpp_kinds.F90"))
    assert "add_library(ccpp_capture_support STATIC" in text
    for name in ("ccpp_kinds.F90", "ccpp_hashable.F90", "ccpp_hash_table.F90",
                 "ccpp_constituent_prop_mod.F90", "ccpp_scheme_utils.F90",
                 "ccpp_capture_mod.F90"):
        assert f'/{name}"' in text
    assert "find_program(NF_CONFIG nf-config REQUIRED)" in text
    # One test per capture directory found; CCPP_CAPTURE_DIR forces one.
    assert 'set(CCPP_CAPTURE_DIR "" CACHE PATH' in text
    assert "function(ccpp_capture_add_tests target scheme)" in text
    assert "set(_name ${target}.${_label})" in text
    # The file-name filter keeps kessler_update's files out of kessler's tests.
    assert ('"^${scheme}_(register|init|timestep_init|run|timestep_final|final)'
            '_[0-9]+\\\\.nc$"') in text
    assert "FATAL_ERROR" not in text
    assert "option(CCPP_CAPTURE_OPENACC" in text
    assert 'file(GLOB _ccpp_capture_tests CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/test_*.cmake")' in text
    assert "enable_testing()" in text


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
    assert os.path.abspath(f"{K}/scheme/kessler.F90") in fragment
    top = (drivers / "CMakeLists.txt").read_text()
    assert str(tmp_path / "out" / "ccpp_kinds.F90") in top
    # Two capture-pass instances share one set of declarations in the cap.
    cap = (tmp_path / "out" / "kessler_suite_cap.F90").read_text()
    assert cap.count("use ccpp_capture_mod, only: ccpp_capture_begin\n") == 1


@pytest.mark.parametrize("spec, expected", [
    ("kessler", ("kessler", "")),
    ("kessler:run", ("kessler", "run")),
    ("kessler:initialize", ("kessler", "initialize")),
    (" kessler : timestep_final ", ("kessler", "timestep_final")),
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
    assert f"'{drivers / 'case.c01b'}')" in cap
    assert "call ccpp_capture_set_info('case.c01b', 'xdsl_ccpp " in cap


@pytest.mark.parametrize("spec", ["kessler:init", "kessler:all", ":run"])
def test_capture_spec_rejects_unknown_phase_or_missing_scheme(spec):
    # A table suffix such as `init` used to capture nothing, silently.
    with pytest.raises(CcppInputError):
        _capture_spec(spec)
