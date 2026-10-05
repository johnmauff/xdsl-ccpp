"""Integration test: run ccpp_xdsl as a subprocess against the capgen example.

Verifies that the CLI entry point is reachable, accepts the standard arguments,
exits cleanly, and writes the expected .F90 cap files to the output directory.
This test exercises the same code path that the CMake module uses via
execute_process().

The test is skipped automatically when ccpp_xdsl is not on PATH (e.g. in a
bare Python environment without the package installed).
"""

import pathlib
import shutil
import subprocess

import pytest

_EXAMPLES = pathlib.Path(__file__).parent.parent.parent / "examples"
_CAP = _EXAMPLES / "capgen"
_SCHEME = _CAP / "scheme"
_HOST_FTN = _CAP / "host_ftn"

# Files that must be present after a successful capgen run.
_EXPECTED_CAPS = {
    "ccpp_kinds.F90",
    "ddt_suite_cap.F90",
    "temp_suite_cap.F90",
    "test_host_ccpp_cap.F90",
}


@pytest.mark.skipif(
    shutil.which("ccpp_xdsl") is None,
    reason="ccpp_xdsl not on PATH — skipping CLI integration test",
)
def test_ccpp_xdsl_generates_caps(tmp_path):
    """ccpp_xdsl exits 0 and writes expected cap files for the capgen example."""
    suites = [
        str(_SCHEME / "ddt_suite.xml"),
        str(_SCHEME / "temp_suite.xml"),
    ]
    scheme_files = [
        str(_SCHEME / "make_ddt.meta"),
        str(_SCHEME / "environ_conditions.meta"),
        str(_SCHEME / "setup_coeffs.meta"),
        str(_SCHEME / "temp_set.meta"),
        str(_SCHEME / "temp_calc_adjust.meta"),
        str(_SCHEME / "temp_adjust.meta"),
    ]
    host_files = [
        str(_HOST_FTN / "test_host_data.meta"),
        str(_HOST_FTN / "test_host_mod.meta"),
        str(_HOST_FTN / "test_host.meta"),
    ]
    tempdir = tmp_path / "tmp"
    tempdir.mkdir()

    result = subprocess.run(
        [
            "ccpp_xdsl",
            "--suites",       ",".join(suites),
            "--scheme-files", ",".join(scheme_files),
            "--host-files",   ",".join(host_files),
            "--host-name",    "test_host",
            "--verbose",      "0",
            "--tempdir",      str(tempdir),
            "-o",             str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"ccpp_xdsl exited {result.returncode}:\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )

    generated = {f.name for f in tmp_path.glob("*.F90")}
    missing = _EXPECTED_CAPS - generated
    assert not missing, (
        f"Expected cap files not generated: {sorted(missing)}\n"
        f"Files found: {sorted(generated)}"
    )


_TINYDDT = _EXAMPLES / "tinyddt"
_TINYDDT_HOST_CPP = _TINYDDT / "host_cpp"

# Files that must be present after a successful chost (C++ host) run --
# both the .F90 caps AND the C++ header/wrapper files, all from a SINGLE
# ccpp_xdsl invocation (cpp-dual-print-pipeline: regression coverage for
# the combined "ftn_and_cpp_header" pipeline target -- no other test
# exercises this through the real CLI entry point end to end).
_EXPECTED_CHOST_FTN_CAPS = {
    "ccpp_kinds.F90",
    "tinyddt_suite_cap.F90",
    "tinyddt_host_ccpp_cap.F90",
    "tinyddt_host_ccpp_chost_cap.F90",
}
_EXPECTED_CHOST_CPP_FILES = {
    "ccpp_kinds.h",
    "tinyddt_host_ccpp_cap.h",
    "tinyddt_host_ccpp_chost_cap.h",
    "tinyddt_host_chost.hpp",
}


@pytest.mark.skipif(
    shutil.which("ccpp_xdsl") is None,
    reason="ccpp_xdsl not on PATH — skipping CLI integration test",
)
def test_ccpp_xdsl_generates_both_ftn_and_cpp_headers_in_one_run(tmp_path):
    """A single ccpp_xdsl run against a C++ host (language = c++ in its
    own host meta, auto-detected -- no --bind-c flag needed) writes both
    the .F90 caps and the C++ .h/.hpp files, all from one pipeline run.

    --verbose 2 so run_pipeline_stage's own command echo lets this test
    assert there was exactly ONE ccpp_opt subprocess invocation -- the
    PR's own defining claim (cpp-dual-print-pipeline). Just checking the
    output files isn't enough: the old two-subprocess implementation
    produced the identical set of files, so a files-only assertion would
    pass unchanged even if this regressed back to two subprocesses
    (Copilot PR #110 review, 2026-10-05).
    """
    tempdir = tmp_path / "tmp"
    tempdir.mkdir()

    result = subprocess.run(
        [
            "ccpp_xdsl",
            "--suites",       str(_TINYDDT / "tinyddt_suite.xml"),
            "--scheme-files", str(_TINYDDT / "tinyddt.meta"),
            "--host-files",   ",".join([
                str(_TINYDDT_HOST_CPP / "tinyddt_host_mod.meta"),
                str(_TINYDDT_HOST_CPP / "tinyddt_host_sub.meta"),
            ]),
            "--host-name",    "tinyddt_host",
            "--verbose",      "2",
            "--tempdir",      str(tempdir),
            "-o",             str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"ccpp_xdsl exited {result.returncode}:\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )

    optimizer_invocations = result.stdout.count("xdsl_ccpp.tools.ccpp_opt")
    assert optimizer_invocations == 1, (
        f"Expected exactly one ccpp_opt subprocess invocation (single "
        f"combined pipeline pass), found {optimizer_invocations}:\n"
        f"stdout: {result.stdout}"
    )

    generated_ftn = {f.name for f in tmp_path.glob("*.F90")}
    missing_ftn = _EXPECTED_CHOST_FTN_CAPS - generated_ftn
    assert not missing_ftn, (
        f"Expected .F90 cap files not generated: {sorted(missing_ftn)}\n"
        f"Files found: {sorted(generated_ftn)}"
    )

    generated_cpp = {f.name for f in tmp_path.glob("*.h")} | {
        f.name for f in tmp_path.glob("*.hpp")
    }
    missing_cpp = _EXPECTED_CHOST_CPP_FILES - generated_cpp
    assert not missing_cpp, (
        f"Expected C++ header/wrapper files not generated: {sorted(missing_cpp)}\n"
        f"Files found: {sorted(generated_cpp)}"
    )


@pytest.mark.skipif(
    shutil.which("ccpp_xdsl") is None,
    reason="ccpp_xdsl not on PATH — skipping CLI integration test",
)
def test_ccpp_xdsl_fails_on_missing_input(tmp_path):
    """ccpp_xdsl exits non-zero when a suite XML file does not exist."""
    result = subprocess.run(
        [
            "ccpp_xdsl",
            "--suites",       str(tmp_path / "nonexistent_suite.xml"),
            "--scheme-files", str(_CAP / "make_ddt.meta"),
            "--host-name",    "test_host",
            "--verbose",      "0",
            "-o",             str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
