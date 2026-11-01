"""The CMake build written next to the scheme I/O capture test drivers
(tools/capture_cmake.py, ccpp_dsl --capture-test-driver-dir)."""

import os

from xdsl_ccpp.tools.capture_cmake import (
    render_capture_cmakelists,
    render_capture_fragment,
    scheme_meta_files,
    support_sources,
)
from xdsl_ccpp.tools.ccpp_dsl import ccppMain

K = "examples/kessler"


def test_fragment_builds_driver_and_scheme_sources_and_registers_the_test():
    text = render_capture_fragment("kessler", ["/src/kessler.F90", "/src/dep.F90"])
    assert "add_executable(test_kessler\n" in text
    assert "${CMAKE_CURRENT_LIST_DIR}/test_kessler.F90" in text
    assert '"/src/kessler.F90"' in text
    assert '"/src/dep.F90"' in text
    assert "target_link_libraries(test_kessler PRIVATE ccpp_capture_support)" in text
    assert ("add_test(NAME test_kessler COMMAND test_kessler "
            "WORKING_DIRECTORY ${CCPP_CAPTURE_DIR})") in text
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
    assert "message(FATAL_ERROR" in text  # CCPP_CAPTURE_DIR is required
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
