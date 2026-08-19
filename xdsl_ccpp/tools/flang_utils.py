"""Shared Flang-invocation helpers for xdsl_ccpp's CLI tools.

Extracted (complexity-audit Tier 1 finding) after `ccpp_validate_fir.py` and
`ccpp_validate_source.py` were found to independently reimplement the same
"search PATH for a Flang binary, then run `flang -fc1 -emit-hlfir ...`" logic
-- and `fir2meta.py`'s own copy had already silently drifted from both:
it hardcoded the literal string ``"flang"`` with no fallback to a versioned
name (``flang-new``/``flang-18``/etc.), and had no ``FileNotFoundError``
handling, so on any system where only a versioned Flang binary is on PATH
(no bare ``flang``) it crashed with an uncaught Python traceback instead of
the clean, documented error message its sibling tools give. Centralizing
the search + invocation here means the three tools can no longer re-diverge
this way; each tool keeps its own "no Flang found" messaging, since that
wording is genuinely call-site-specific (e.g. `--backend flang` requested
vs. Flang preferred-but-optional).
"""

from __future__ import annotations

import shutil
import subprocess
import sys

FLANG_CANDIDATES = ("flang", "flang-new", "flang-20", "flang-19", "flang-18")


def find_flang() -> str | None:
    """Return the name of the first available Flang executable, or None."""
    for candidate in FLANG_CANDIDATES:
        if shutil.which(candidate):
            return candidate
    return None


def run_flang(flang: str, f90_file: str, fir_mlir: str, verbose: bool = False) -> bool:
    """Run ``<flang> -fc1 -emit-hlfir ...`` on f90_file, writing FIR MLIR to fir_mlir.

    Caller resolves `flang` via find_flang() first and handles the
    not-found case itself (each tool's own error message/exit behavior
    differs).
    """
    cmd = [
        flang, "-fc1", "-emit-hlfir",
        "-mmlir", "-mlir-print-op-generic",
        f90_file, "-o", fir_mlir,
    ]
    if verbose:
        print(f"  flang: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print(f"Error: could not execute '{flang}'", file=sys.stderr)
        return False
    if result.returncode != 0:
        print(f"Error: flang failed on '{f90_file}':\n{result.stderr}", file=sys.stderr)
        return False
    return True
