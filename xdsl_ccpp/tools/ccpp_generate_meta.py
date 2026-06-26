"""Generate CCPP .meta skeleton files from Fortran source.

Extracts argument metadata (name, type, kind, intent, dimensions, optional) from
Fortran subroutine signatures and writes ``.meta`` files with stub values for
fields that cannot be inferred from source (``standard_name``, ``units``,
dimension standard names).

Matches the functionality of ``ccpp_fortran_to_metadata.py`` from capgen-ng.

Only subroutines following the CCPP entry-point naming convention are emitted:
names ending in ``_run``, ``_init``, ``_finalize``, ``_final``,
``_timestep_init``, or ``_timestep_final``.  All other subroutines in the
module are skipped.

Usage::

    ccpp_generate_meta scheme.F90
    ccpp_generate_meta --output-dir out/ scheme_a.F90 scheme_b.F90
    ccpp_generate_meta --stdout scheme.F90
"""
from __future__ import annotations

import argparse
import itertools
import os
import sys

from xdsl.dialects import builtin
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp import ArgumentOp, ArgumentTableOp, TablePropertiesOp


_CCPP_ENTRY_SUFFIXES = (
    "_run",
    "_init",
    "_finalize",
    "_final",
    "_timestep_init",
    "_timestep_final",
)


def _is_ccpp_entry(name: str) -> bool:
    """Return True if *name* ends with a CCPP lifecycle entry-point suffix."""
    return name.lower().endswith(_CCPP_ENTRY_SUFFIXES)


def meta_from_module(module_op: builtin.ModuleOp, *, filter_entries: bool = True) -> str:
    """Serialize a MLIR module of CCPP table ops to ``.meta`` text format.

    Args:
        module_op: A ``builtin.ModuleOp`` produced by
            ``fparser2_to_meta.build_meta_module_from_source``.
        filter_entries: When ``True``, only emit ``[ccpp-arg-table]`` blocks for
            subroutines matching the CCPP entry-point naming convention.

    Returns:
        A string in ``.meta`` format ready to write to a file, or an empty
        string when no matching entry points are found.
    """
    counter = itertools.count(1)

    def next_stub() -> str:
        return f"std_name_{next(counter):03d}"

    lines: list[str] = []
    first_block = True

    for op in module_op.body.block.ops:
        if not isa(op, TablePropertiesOp):
            continue

        scheme_name = op.table_name.data

        entry_points = [
            at for at in op.body.block.ops
            if isa(at, ArgumentTableOp)
            and (not filter_entries or _is_ccpp_entry(at.table_name.data))
        ]

        if not entry_points:
            continue

        if not first_block:
            lines.append("")
        first_block = False

        lines.append("[ccpp-table-properties]")
        lines.append(f"  name = {scheme_name}")
        lines.append(f"  type = scheme")
        lines.append("")

        for arg_table in entry_points:
            lines.append("[ccpp-arg-table]")
            lines.append(f"  name = {arg_table.table_name.data}")
            lines.append(f"  type = scheme")

            for arg in arg_table.body.block.ops:
                if not isa(arg, ArgumentOp):
                    continue

                local_name = arg.arg_name.data
                arg_type = arg.arg_type.data
                kind = arg.kind.data if arg.kind is not None else None
                intent = arg.intent.data if arg.intent is not None else None
                dim_count = arg.dimensions.data if arg.dimensions is not None else 0
                dim_names_raw = arg.dim_names.data if arg.dim_names is not None else ""
                is_optional = arg.optional is not None

                lines.append(f"[ {local_name} ]")
                lines.append(f"  standard_name = {next_stub()}")
                lines.append(f"  units = enter_units")
                lines.append(f"  type = {arg_type}")
                if kind:
                    lines.append(f"  kind = {kind}")
                if dim_count == 0:
                    lines.append(f"  dimensions = ()")
                else:
                    if dim_names_raw:
                        dim_list = [d.strip() for d in dim_names_raw.split(",") if d.strip()]
                    else:
                        dim_list = [next_stub() for _ in range(dim_count)]
                    lines.append(f"  dimensions = ({', '.join(dim_list)})")
                if intent:
                    lines.append(f"  intent = {intent}")
                if is_optional:
                    lines.append(f"  optional = True")

            lines.append("")

    while lines and not lines[-1]:
        lines.pop()

    return "\n".join(lines) + "\n" if lines else ""


def generate_meta_for_file(f90_path: str) -> str | None:
    """Extract CCPP metadata from *f90_path* and return ``.meta`` text.

    Returns ``None`` if fparser is not installed or extraction fails.
    """
    try:
        from xdsl_ccpp.transforms.fparser2_to_meta import build_meta_module_from_file
    except ImportError:
        print(
            "Error: fparser is not installed.  Install it with:  pip install fparser",
            file=sys.stderr,
        )
        return None

    try:
        module_op = build_meta_module_from_file(f90_path)
    except Exception as exc:
        print(f"Error: fparser2 failed on '{f90_path}': {exc}", file=sys.stderr)
        return None

    return meta_from_module(module_op)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate CCPP .meta skeleton files from Fortran source.  "
            "Fields that cannot be inferred (standard_name, units, dimension names) "
            "are filled with stub values to be replaced by the developer."
        )
    )
    parser.add_argument(
        "f90_files",
        nargs="+",
        metavar="FILE.F90",
        help="Fortran source files to extract metadata from.",
    )
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        default=None,
        help="Write .meta files here (default: same directory as each .F90).",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print all output to stdout instead of writing files.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print the output path for each generated file.",
    )
    args = parser.parse_args(argv)

    any_errors = False

    for f90_file in args.f90_files:
        if not os.path.isfile(f90_file):
            print(f"Error: file not found: '{f90_file}'", file=sys.stderr)
            any_errors = True
            continue

        meta_text = generate_meta_for_file(f90_file)
        if meta_text is None:
            any_errors = True
            continue

        if not meta_text.strip():
            print(
                f"Warning: no CCPP entry-point subroutines found in "
                f"'{os.path.basename(f90_file)}' "
                f"(expected suffixes: {', '.join(_CCPP_ENTRY_SUFFIXES)})",
                file=sys.stderr,
            )
            continue

        if args.stdout:
            print(meta_text, end="")
        else:
            stem = os.path.splitext(os.path.basename(f90_file))[0]
            out_dir = args.output_dir or os.path.dirname(os.path.abspath(f90_file))
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{stem}.meta")
            with open(out_path, "w") as f:
                f.write(meta_text)
            if args.verbose:
                print(f"Wrote: {out_path}")

    sys.exit(1 if any_errors else 0)


if __name__ == "__main__":
    main()
