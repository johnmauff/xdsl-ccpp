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
