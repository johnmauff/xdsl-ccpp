"""ccpp_validate_fir — Validate CCPP .meta files against Fortran source via Flang FIR.

For each ``.F90`` file the tool:
1. Looks for a ``.meta`` file with the same stem in the same directory
   (override with ``--meta-dir``).
2. Runs ``flang -fc1 -emit-hlfir`` to produce FIR MLIR.
3. Runs the ``fir-to-meta`` pass to extract CCPP metadata from FIR.
4. Loads the ``.meta`` file.
5. Compares: reports type, rank, intent, and optional mismatches.

Usage example::

    python3 -m xdsl_ccpp.tools.ccpp_validate_fir examples/capgen/temp_adjust.F90

Exit code is 0 if all validated files match, 1 if any mismatches are found
or any step fails.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

from xdsl.context import Context
from xdsl.dialects import builtin
from xdsl.parser import Parser
from xdsl.universe import Universe

from xdsl_ccpp.dialects.ccpp import CCPP, TablePropertiesOp
from xdsl_ccpp.dialects.ccpp_utils import CCPPUtils
from xdsl_ccpp.frontend.ccpp_xml import ccppXML, parse_meta_file
from xdsl_ccpp.transforms.validate_fir import compare_modules


def _make_ctx() -> Context:
    ctx = Context()
    for name, factory in Universe.get_multiverse().all_dialects.items():
        ctx.register_dialect(name, factory)
    ctx.load_dialect(CCPP)
    ctx.load_dialect(CCPPUtils)
    return ctx


def _find_flang() -> str | None:
    """Return the name of the first available Flang executable, or None."""
    import shutil
    for candidate in ("flang", "flang-new", "flang-20", "flang-19", "flang-18"):
        if shutil.which(candidate):
            return candidate
    return None


def _run_flang(f90_file: str, fir_mlir: str) -> bool:
    flang = _find_flang()
    if flang is None:
        print(
            "Error: no Flang executable found on PATH.\n"
            "  Tried: flang, flang-new, flang-18/19/20\n"
            "  Install via:  brew install llvm   (then add $(brew --prefix llvm)/bin to PATH)\n"
            "             or conda install -c conda-forge flang",
            file=sys.stderr,
        )
        return False
    cmd = [
        flang, "-fc1", "-emit-hlfir",
        "-mmlir", "-mlir-print-op-generic",
        f90_file, "-o", fir_mlir,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print(f"Error: could not execute '{flang}'", file=sys.stderr)
        return False
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


def _load_meta_file(meta_path: str) -> builtin.ModuleOp | None:
    """Parse a .meta file and return a ModuleOp containing its TablePropertiesOps."""
    try:
        frontend = ccppXML()
        props = []
        for meta in parse_meta_file(meta_path, True):
            props.append(frontend.build_meta_ir(meta))
        if not props:
            print(f"Warning: no tables found in '{meta_path}'", file=sys.stderr)
            return None
        return builtin.ModuleOp(props)
    except Exception as exc:
        print(f"Error loading '{meta_path}': {exc}", file=sys.stderr)
        return None


def _parse_mlir(text: str) -> builtin.ModuleOp | None:
    try:
        return Parser(_make_ctx(), text).parse_op()
    except Exception as exc:
        print(f"Error parsing MLIR output: {exc}", file=sys.stderr)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate CCPP .meta files against Fortran source via Flang FIR"
    )
    parser.add_argument("f90_files", nargs="+", metavar="FILE.F90")
    parser.add_argument(
        "--meta-dir",
        help="Directory containing .meta files (default: same directory as each .F90)",
    )
    args = parser.parse_args()

    any_errors = False

    with tempfile.TemporaryDirectory() as tmpdir:
        for f90_file in args.f90_files:
            stem = os.path.splitext(os.path.basename(f90_file))[0]
            meta_dir = args.meta_dir or os.path.dirname(os.path.abspath(f90_file))
            meta_file = os.path.join(meta_dir, f"{stem}.meta")

            if not os.path.exists(meta_file):
                print(f"Skipping '{f90_file}': no .meta file at '{meta_file}'")
                continue

            print(f"Validating '{os.path.basename(f90_file)}' against '{os.path.basename(meta_file)}'...")

            fir_mlir = os.path.join(tmpdir, f"{stem}.mlir")

            if not _run_flang(f90_file, fir_mlir):
                any_errors = True
                continue

            meta_text = _run_fir_to_meta(fir_mlir)
            if meta_text is None:
                any_errors = True
                continue

            fir_module = _parse_mlir(meta_text)
            if fir_module is None:
                any_errors = True
                continue

            meta_module = _load_meta_file(meta_file)
            if meta_module is None:
                any_errors = True
                continue

            mismatches = compare_modules(meta_module, fir_module)

            if not mismatches:
                print("  OK")
            else:
                any_errors = True
                for m in mismatches:
                    print(str(m))

    sys.exit(1 if any_errors else 0)


if __name__ == "__main__":
    main()
