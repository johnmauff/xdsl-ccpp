"""ccpp_validate_source — Validate CCPP .meta files against Fortran source.

Fortran source is parsed with fparser2 (``pip install fparser``, the
``validate`` extra), a pure-Python Fortran parser.

For each ``.F90`` file the tool finds a ``.meta`` file with the same stem in
the same directory (override with ``--meta-dir``), then compares:
- argument existence (in .meta but not source, or vice versa)
- type  (``real``, ``integer``, ``character``)
- rank  (number of array dimensions)
- intent (``in``, ``out``, ``inout``)
- optional flag

Usage::

    python -m xdsl_ccpp.tools.ccpp_validate_source examples/capgen/*.F90

Exit code is 0 when all validated files match, 1 on any mismatch or error.
"""

from __future__ import annotations

import argparse
import os
import sys

from xdsl.dialects import builtin

from xdsl_ccpp.frontend.ccpp_xml import ccppXML, parse_meta_file
from xdsl_ccpp.transforms.validate_source import (
    check_dimension_names,
    collect_standard_names,
    compare_modules,
)
from xdsl_ccpp.util.optional_deps import fparser_available

# ── fparser2 ──────────────────────────────────────────────────────────────────

def _require_fparser() -> None:
    """Exit with a helpful message if fparser is not installed."""
    if not fparser_available():
        print(
            "Error: ccpp_validate needs fparser.\n"
            "  Install via:  pip install fparser",
            file=sys.stderr,
        )
        sys.exit(1)


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
                 for m in parse_meta_file(meta_path, True)]
        return builtin.ModuleOp(props) if props else None
    except Exception as exc:
        print(f"Error loading '{meta_path}': {exc}", file=sys.stderr)
        return None


def _load_meta_file(meta_path: str, verbose: bool = False) -> builtin.ModuleOp | None:
    """Load a scheme .meta file.  Returns None if the file is a host/module type."""
    from xdsl_ccpp.dialects.ccpp import TableTypeKind
    from xdsl_ccpp.transforms.validate_source import _collect_arg_tables
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
        "-v", "--verbose",
        action="store_true",
        help="Print skipped files",
    )
    args = parser.parse_args()

    _require_fparser()

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
