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

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


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
