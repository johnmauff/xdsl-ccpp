"""fir2meta — Compile Fortran F90 files to CCPP metadata via Flang FIR.

For each input F90 file the tool:

1. Runs ``flang -fc1 -emit-hlfir -mmlir -mlir-print-op-generic <file>`` to
   produce FIR MLIR in a temporary directory.
2. Runs ``python3 -m xdsl_ccpp.tools.ccpp_opt <fir.mlir> -p fir-to-meta`` to
   extract CCPP dialect metadata from the FIR.
3. Accumulates all generated ``ccpp.table_properties`` ops into a single
   ``builtin.module @ccpp_meta``.

The accumulated module is written to ``meta.mlir`` (or the path given via
``-o``).

Usage example::

    python3 -m xdsl_ccpp.tools.fir2meta hello_scheme.F90 temp_adjust.F90 -o meta.mlir
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from xdsl.context import Context
from xdsl.dialects import builtin
from xdsl.dialects.builtin import StringAttr
from xdsl.parser import Parser
from xdsl.printer import Printer
from xdsl.universe import Universe

from xdsl_ccpp.dialects.ccpp import CCPP, TablePropertiesOp
from xdsl_ccpp.dialects.ccpp_utils import CCPPUtils
from xdsl_ccpp.tools.flang_utils import find_flang, run_flang


def _make_ctx() -> Context:
    """Build a Context with all standard + CCPP dialects loaded."""
    ctx = Context()
    for name, factory in Universe.get_multiverse().all_dialects.items():
        ctx.register_dialect(name, factory)
    ctx.load_dialect(CCPP)
    ctx.load_dialect(CCPPUtils)
    return ctx


def _parse_mlir_str(text: str) -> builtin.ModuleOp:
    ctx = _make_ctx()
    return Parser(ctx, text).parse_op()


def _run_fir_to_meta(fir_mlir: str, verbose: bool) -> str | None:
    """Run the fir-to-meta pass on *fir_mlir* and return the MLIR output string."""
    cmd = [
        sys.executable,
        "-m",
        "xdsl_ccpp.tools.ccpp_opt",
        fir_mlir,
        "-p",
        "fir-to-meta",
    ]
    if verbose:
        print(f"  fir-to-meta: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(
            f"Error: fir-to-meta failed on '{fir_mlir}':\n{result.stderr}",
            file=sys.stderr,
        )
        return None
    return result.stdout


def _extract_table_props(meta_module: builtin.ModuleOp) -> list[TablePropertiesOp]:
    """Detach and return all ``ccpp.table_properties`` ops from the first
    ``builtin.module @ccpp_meta`` found inside *meta_module*."""
    for child in meta_module.body.block.ops:
        if not isinstance(child, builtin.ModuleOp):
            continue
        props: list[TablePropertiesOp] = []
        for op in list(child.body.block.ops):
            if isinstance(op, TablePropertiesOp):
                op.detach()
                props.append(op)
        return props
    return []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile F90 files to CCPP metadata via Flang FIR"
    )
    parser.add_argument(
        "f90_files",
        nargs="+",
        metavar="FILE.F90",
        help="Fortran source files to process",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="meta.mlir",
        help="Output metadata file (default: meta.mlir)",
    )
    parser.add_argument(
        "-t",
        "--tmpdir",
        default="tmp",
        help="Temporary directory for FIR MLIR files (default: tmp)",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Keep temporary FIR MLIR files after completion",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print each command before running it",
    )
    args = parser.parse_args()

    # Validate inputs up front
    missing = [f for f in args.f90_files if not os.path.exists(f)]
    if missing:
        for f in missing:
            print(f"Error: input file not found: '{f}'", file=sys.stderr)
        sys.exit(1)

    flang = find_flang()
    if flang is None:
        print(
            "Error: no Flang executable found on PATH.\n"
            "  Tried: flang, flang-new, flang-18/19/20\n"
            "  Install via:  brew install llvm   (then add $(brew --prefix llvm)/bin to PATH)\n"
            "             or conda install -c conda-forge flang",
            file=sys.stderr,
        )
        sys.exit(1)

    os.makedirs(args.tmpdir, exist_ok=True)

    # Accumulation module: a single @ccpp_meta ModuleOp that collects all
    # ccpp.table_properties ops as they are generated.
    acc_ccpp_meta: builtin.ModuleOp | None = None
    fir_files: list[str] = []

    for f90_file in args.f90_files:
        basename = os.path.splitext(os.path.basename(f90_file))[0]
        fir_mlir = os.path.join(args.tmpdir, f"{basename}.mlir")
        fir_files.append(fir_mlir)

        print(f"Processing '{f90_file}'...")

        # Step 1: F90 → FIR MLIR via Flang
        if not run_flang(flang, f90_file, fir_mlir, args.verbose):
            sys.exit(1)

        # Step 2: FIR MLIR → CCPP metadata via fir-to-meta pass
        meta_text = _run_fir_to_meta(fir_mlir, args.verbose)
        if meta_text is None:
            sys.exit(1)

        # Step 3: parse the output and extract table_properties ops
        try:
            meta_module = _parse_mlir_str(meta_text)
        except Exception as exc:
            print(
                f"Error: failed to parse fir-to-meta output for '{f90_file}': {exc}",
                file=sys.stderr,
            )
            sys.exit(1)

        table_props = _extract_table_props(meta_module)
        if not table_props:
            print(
                f"Warning: no CCPP metadata generated from '{f90_file}'",
                file=sys.stderr,
            )
            continue

        # Step 4: accumulate into the running @ccpp_meta module
        if acc_ccpp_meta is None:
            acc_ccpp_meta = builtin.ModuleOp([], sym_name=StringAttr("ccpp_meta"))

        for prop in table_props:
            acc_ccpp_meta.body.block.add_op(prop)

        print(f"  -> added {len(table_props)} table_properties block(s)")

    if acc_ccpp_meta is None:
        print("Error: no CCPP metadata was generated.", file=sys.stderr)
        sys.exit(1)

    # Wrap the accumulated module in a top-level builtin.module and write
    top_module = builtin.ModuleOp([acc_ccpp_meta])
    with open(args.output, "w") as f:
        printer = Printer(stream=f)
        printer.print_op(top_module)
        f.write("\n")

    print(f"Written: '{args.output}'")

    # Cleanup temporary FIR MLIR files unless --debug is set
    if not args.debug:
        for path in fir_files:
            if os.path.exists(path):
                os.remove(path)
        if os.path.isdir(args.tmpdir) and not os.listdir(args.tmpdir):
            os.rmdir(args.tmpdir)


if __name__ == "__main__":
    main()
