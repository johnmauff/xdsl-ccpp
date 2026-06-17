"""ccpp_validate_source — Validate CCPP .meta files against Fortran source.

Automatically selects the best available backend:

1. **Flang** (``flang`` / ``flang-new`` on PATH): uses the production Fortran
   compiler frontend via the ``fir-to-meta`` pass — the most robust option.
2. **fparser2** (``pip install fparser``): pure-Python Fortran parser — no
   external tools required, sufficient for well-formed CCPP scheme files.

For each ``.F90`` file the tool finds a ``.meta`` file with the same stem in
the same directory (override with ``--meta-dir``), then compares:
- argument existence (in .meta but not source, or vice versa)
- type  (``real``, ``integer``, ``character``)
- rank  (number of array dimensions)
- intent (``in``, ``out``, ``inout``)
- optional flag

Usage::

    python -m xdsl_ccpp.tools.ccpp_validate_source examples/capgen/*.F90
    python -m xdsl_ccpp.tools.ccpp_validate_source --backend fparser2 scheme.F90
    python -m xdsl_ccpp.tools.ccpp_validate_source --backend flang scheme.F90

Exit code is 0 when all validated files match, 1 on any mismatch or error.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

from xdsl.context import Context
from xdsl.dialects import builtin
from xdsl.parser import Parser
from xdsl.universe import Universe

from xdsl_ccpp.dialects.ccpp import CCPP
from xdsl_ccpp.dialects.ccpp_utils import CCPPUtils
from xdsl_ccpp.frontend.ccpp_xml import ccppXML
from xdsl_ccpp.transforms.validate_fir import (
    check_dimension_names,
    collect_standard_names,
    compare_modules,
)


# ── backend detection ─────────────────────────────────────────────────────────

def _find_flang() -> str | None:
    for candidate in ("flang", "flang-new", "flang-20", "flang-19", "flang-18"):
        if shutil.which(candidate):
            return candidate
    return None


def _fparser_available() -> bool:
    try:
        import fparser.two.Fortran2003  # noqa: F401
        return True
    except ImportError:
        return False


def _select_backend(requested: str | None) -> str:
    """Return 'flang' or 'fparser2', or exit with a helpful message."""
    if requested == "flang":
        if _find_flang() is None:
            print(
                "Error: --backend flang requested but no Flang executable found.\n"
                "  Install via:  brew install llvm  (add $(brew --prefix llvm)/bin to PATH)\n"
                "             or conda install -c conda-forge flang",
                file=sys.stderr,
            )
            sys.exit(1)
        return "flang"
    if requested == "fparser2":
        if not _fparser_available():
            print(
                "Error: --backend fparser2 requested but fparser is not installed.\n"
                "  Install via:  pip install fparser",
                file=sys.stderr,
            )
            sys.exit(1)
        return "fparser2"
    # Auto-detect
    if _find_flang():
        return "flang"
    if _fparser_available():
        return "fparser2"
    print(
        "Error: no Fortran parsing backend available.\n"
        "  Option 1 (pure Python, no root):  pip install fparser\n"
        "  Option 2 (production compiler):   brew install llvm  "
        "or conda install -c conda-forge flang",
        file=sys.stderr,
    )
    sys.exit(1)


# ── Flang pipeline ────────────────────────────────────────────────────────────

def _make_ctx() -> Context:
    ctx = Context()
    for name, factory in Universe.get_multiverse().all_dialects.items():
        ctx.register_dialect(name, factory)
    ctx.load_dialect(CCPP)
    ctx.load_dialect(CCPPUtils)
    return ctx


def _run_flang(flang: str, f90_file: str, fir_mlir: str) -> bool:
    cmd = [
        flang, "-fc1", "-emit-hlfir",
        "-mmlir", "-mlir-print-op-generic",
        f90_file, "-o", fir_mlir,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: flang failed on '{f90_file}':\n{result.stderr}", file=sys.stderr)
        return False
    return True


def _run_fir_to_meta(fir_mlir: str) -> str | None:
    cmd = [sys.executable, "-m", "xdsl_ccpp.tools.ccpp_opt", fir_mlir, "-p", "fir-to-meta"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: fir-to-meta failed:\n{result.stderr}", file=sys.stderr)
        return None
    return result.stdout


def _extract_fir(flang: str, f90_file: str, tmpdir: str) -> builtin.ModuleOp | None:
    stem = os.path.splitext(os.path.basename(f90_file))[0]
    fir_mlir = os.path.join(tmpdir, f"{stem}.mlir")
    if not _run_flang(flang, f90_file, fir_mlir):
        return None
    meta_text = _run_fir_to_meta(fir_mlir)
    if meta_text is None:
        return None
    try:
        return Parser(_make_ctx(), meta_text).parse_op()
    except Exception as exc:
        print(f"Error: failed to parse fir-to-meta output: {exc}", file=sys.stderr)
        return None


# ── fparser2 pipeline ─────────────────────────────────────────────────────────

def _extract_fparser2(f90_file: str) -> builtin.ModuleOp | None:
    from xdsl_ccpp.transforms.fparser2_to_meta import build_meta_module_from_file
    try:
        return build_meta_module_from_file(f90_file)
    except Exception as exc:
        print(f"Error: fparser2 failed on '{f90_file}': {exc}", file=sys.stderr)
        return None


# ── .meta loader ─────────────────────────────────────────────────────────────

def _parse_meta_file(meta_path: str) -> builtin.ModuleOp | None:
    """Parse any .meta file into CCPP IR; returns None only on error."""
    try:
        frontend = ccppXML()
        props = [frontend.build_meta_ir(m)
                 for m in frontend.parse_metadata_file(meta_path, True)]
        return builtin.ModuleOp(props) if props else None
    except Exception as exc:
        print(f"Error loading '{meta_path}': {exc}", file=sys.stderr)
        return None


def _load_meta_file(meta_path: str, verbose: bool = False) -> builtin.ModuleOp | None:
    """Load a scheme .meta file.  Returns None if the file is a host/module type."""
    from xdsl_ccpp.transforms.validate_fir import _collect_arg_tables
    from xdsl_ccpp.dialects.ccpp import TableTypeKind
    module = _parse_meta_file(meta_path)
    if module is None:
        return None
    tables = _collect_arg_tables(module)
    scheme_tables = [
        t for t in tables.values()
        if t.table_type.data == TableTypeKind.Scheme
    ]
    if not scheme_tables:
        if verbose:
            print(f"Skipping '{os.path.basename(meta_path)}': no scheme-type arg tables")
        return None
    return module


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate CCPP .meta files against Fortran source"
    )
    parser.add_argument("f90_files", nargs="+", metavar="FILE.F90")
    parser.add_argument(
        "--meta-dir",
        help="Directory containing .meta files (default: same directory as each .F90)",
    )
    parser.add_argument(
        "--host-files",
        metavar="HOST.meta,...",
        help="Comma-separated host model .meta files; enables dimension name validation",
    )
    parser.add_argument(
        "--backend",
        choices=["flang", "fparser2"],
        help="Fortran parsing backend (default: auto-detect, preferring flang)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print skipped files and backend selection",
    )
    args = parser.parse_args()

    backend = _select_backend(args.backend)
    flang = _find_flang() if backend == "flang" else None
    if args.verbose:
        print(f"Backend: {backend}" + (f" ({flang})" if flang else ""))

    # Build the known-standard-names set for dimension checking.
    # Requires --host-files; we also include standard names from the scheme .meta
    # files in this run so that loop-extent variables (e.g. horizontal_loop_extent)
    # declared as scheme arguments are recognised as valid dimension names.
    known_names: set[str] = set()
    if args.host_files:
        for hp in (p.strip() for p in args.host_files.split(",")):
            mod = _parse_meta_file(hp)
            if mod is not None:
                known_names |= collect_standard_names(mod)
        for f90_file in args.f90_files:
            stem = os.path.splitext(os.path.basename(f90_file))[0]
            meta_dir = args.meta_dir or os.path.dirname(os.path.abspath(f90_file))
            meta_path = os.path.join(meta_dir, f"{stem}.meta")
            if os.path.exists(meta_path):
                mod = _parse_meta_file(meta_path)
                if mod is not None:
                    known_names |= collect_standard_names(mod)

    any_errors = False

    with tempfile.TemporaryDirectory() as tmpdir:
        for f90_file in args.f90_files:
            stem = os.path.splitext(os.path.basename(f90_file))[0]
            meta_dir = args.meta_dir or os.path.dirname(os.path.abspath(f90_file))
            meta_file = os.path.join(meta_dir, f"{stem}.meta")

            if not os.path.exists(meta_file):
                if args.verbose:
                    print(f"Skipping '{os.path.basename(f90_file)}': no matching .meta file")
                continue

            # Load the .meta file first — silently skip host/module-type files
            meta_module = _load_meta_file(meta_file, verbose=args.verbose)
            if meta_module is None:
                continue

            print(f"Validating '{os.path.basename(f90_file)}' against '{os.path.basename(meta_file)}'...")

            if backend == "flang":
                source_module = _extract_fir(flang, f90_file, tmpdir)
            else:
                source_module = _extract_fparser2(f90_file)

            if source_module is None:
                any_errors = True
                continue

            mismatches = compare_modules(meta_module, source_module)
            if known_names:
                mismatches += check_dimension_names(meta_module, known_names)

            if not mismatches:
                print("  OK")
            else:
                any_errors = True
                for m in mismatches:
                    print(str(m))

    sys.exit(1 if any_errors else 0)


if __name__ == "__main__":
    main()
