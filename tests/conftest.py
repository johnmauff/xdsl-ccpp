"""pytest integration for filecheck-style tests.

Discovers all ``*.mlir`` files under ``tests/filecheck/``, extracts their
``// RUN:`` directives, and executes each as a shell command from the
repository root.  The ``%s`` placeholder in each RUN line is replaced with the
absolute path to the test file, following the LLVM FileCheck convention.

A file may also carry a ``// XFAIL: <reason>`` directive (same convention as
LLVM lit) to mark a known, tracked failure — the test still runs, but a
failure is reported as expected instead of breaking the suite.

Usage::

    pytest tests/

"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from xdsl_ccpp.tools.ccpp_opt import VERIFY_EACH_PASS_ENV

REPO_ROOT = Path(__file__).parent.parent

# Tests verify the IR after every pass (ccpp_opt --verify-each-pass), so a
# pass that leaves invalid IR is caught at that pass; the RUN lines' and the
# generator's ccpp_opt subprocesses inherit this.
os.environ.setdefault(VERIFY_EACH_PASS_ENV, "1")

# Subprocesses (the RUN lines' python3, the ccpp_xdsl entry point in
# test_build_integration.py) come from the environment running pytest, even
# when its bin directory is not on PATH (venv/bin/python -m pytest without
# activating the venv). Not resolved: a venv's python is a symlink.
_BIN_DIR = os.path.dirname(sys.executable)
if _BIN_DIR not in os.environ.get("PATH", "").split(os.pathsep):
    os.environ["PATH"] = os.pathsep.join(
        p for p in (_BIN_DIR, os.environ.get("PATH")) if p
    )


def pytest_collect_file(parent, file_path):
    if file_path.suffix == ".mlir" and "filecheck" in str(file_path):
        return FilecheckFile.from_parent(parent, path=file_path)


class FilecheckFile(pytest.File):
    def collect(self):
        content = self.path.read_text()
        run_cmds = []
        xfail_reason = None
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("// RUN:"):
                run_cmds.append(stripped[len("// RUN:") :].strip())
            elif stripped.startswith("// XFAIL:"):
                xfail_reason = stripped[len("// XFAIL:") :].strip()
        for idx, cmd in enumerate(run_cmds):
            name = "run" if len(run_cmds) == 1 else f"run{idx}"
            item = FilecheckItem.from_parent(self, name=name, cmd=cmd)
            if xfail_reason:
                item.add_marker(pytest.mark.xfail(reason=xfail_reason, strict=False))
            yield item


class FilecheckItem(pytest.Item):
    def __init__(self, *, cmd: str, **kwargs):
        super().__init__(**kwargs)
        self.cmd = cmd.replace("%s", str(self.fspath))

    def runtest(self):
        result = subprocess.run(
            self.cmd,
            shell=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise FilecheckFailure(self.cmd, result.stdout, result.stderr)

    def repr_failure(self, excinfo):
        if isinstance(excinfo.value, FilecheckFailure):
            e = excinfo.value
            parts = [f"Command: {e.cmd}"]
            if e.stdout:
                parts.append(f"stdout:\n{e.stdout}")
            if e.stderr:
                parts.append(f"stderr:\n{e.stderr}")
            return "\n".join(parts)
        return super().repr_failure(excinfo)

    def reportinfo(self):
        return self.fspath, 0, f"filecheck: {self.fspath.basename}::{self.name}"


class FilecheckFailure(Exception):
    def __init__(self, cmd: str, stdout: str, stderr: str):
        self.cmd = cmd
        self.stdout = stdout
        self.stderr = stderr
