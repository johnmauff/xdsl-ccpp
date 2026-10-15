"""ccpp_validate_driver — Check a host-driver program's own error-handling
locals against the CCPP protocol's fixed convention.

Generated CCPP caps always declare their public ``errmsg``/``errflg``
lifecycle arguments with a fixed shape -- ``character(len=CCPP_ERRMSG_LEN)``
/ ``integer`` (``CCPP_ERRMSG_LEN`` is a framework-wide protocol constant in
``xdsl_ccpp/util/ccpp_conventions.py``, not something read back out of any
``.meta`` file: "The CCPP specification mandates 512"). A host driver
program (e.g. ``examples/*/main.F90``) that calls those generated lifecycle
subroutines directly must declare its own local ``errmsg``/``errflg`` to
match -- if it doesn't, the mismatch is a real Fortran standard violation
under an explicit interface. Some compilers (Intel ``ifx``) catch it at
build time; others (gfortran) silently tolerate it.

No ``.meta`` file describes a driver program's own local variables in this
repo (unlike a scheme's dummy arguments, which real ``.meta`` files do
describe) -- so this tool parses the driver's own ``program ... end
program`` block via fparser2
(``xdsl_ccpp.transforms.fparser2_to_meta.extract_program_locals``) and
compares what it actually declared against the protocol's known-correct
shape, reusing the same comparison/formatting machinery
(``compare_arg_tables``/``Mismatch``) already used to validate scheme
``.meta`` files against their own Fortran source.

Usage::

    python -m xdsl_ccpp.tools.ccpp_validate_driver examples/*/main.F90

Exit code is 0 when every file's program block (if any) matches the
protocol convention, 1 on any mismatch or parse error.
"""

from __future__ import annotations

import argparse
import sys

from xdsl_ccpp.dialects.ccpp import ArgumentOp, ArgumentTableOp
from xdsl_ccpp.transforms.validate_fir import Mismatch, compare_arg_tables
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_ERRFLG_LOCAL,
    CCPP_ERRMSG_LEN,
    CCPP_ERRMSG_LOCAL,
)

_CHECKED_NAMES = {CCPP_ERRMSG_LOCAL, CCPP_ERRFLG_LOCAL}


def _fparser_available() -> bool:
    try:
        import fparser.two.Fortran2003  # noqa: F401
        return True
    except ImportError:
        return False


def _dims_attr(rank: int) -> str:
    if rank <= 0:
        return "()"
    return "(" + ", ".join(f"dim{i + 1}" for i in range(rank)) + ")"


def _expected_table(table_name: str) -> ArgumentTableOp:
    """The CCPP protocol's fixed shape for a driver's own errmsg/errflg."""
    errmsg = ArgumentOp(
        CCPP_ERRMSG_LOCAL, "character",
        {"type": "character", "kind": f"len={CCPP_ERRMSG_LEN}", "dimensions": "()"},
    )
    errflg = ArgumentOp(
        CCPP_ERRFLG_LOCAL, "integer",
        {"type": "integer", "dimensions": "()"},
    )
    return ArgumentTableOp(table_name, "scheme", [errmsg, errflg])


def _actual_table(table_name: str, args: list[dict]) -> ArgumentTableOp:
    arg_ops = []
    for attrs in args:
        op_attrs: dict = {"type": attrs["type"], "dimensions": _dims_attr(attrs["rank"])}
        if attrs.get("kind"):
            op_attrs["kind"] = attrs["kind"]
        elif attrs["type"] == "character":
            # An omitted character selector is a real declaration (Fortran's
            # own default is len=1), not an absence of information -- compare_
            # arg_tables only compares kind when BOTH tables supply one, so
            # leaving this unset here would silently skip the comparison
            # entirely for a bare `character :: errmsg`, passing it as if it
            # matched the expected len=512.
            op_attrs["kind"] = "len=1"
        arg_ops.append(ArgumentOp(attrs["name"], attrs["type"], op_attrs))
    return ArgumentTableOp(table_name, "scheme", arg_ops)


def check_driver_file(f90_path: str) -> list[Mismatch]:
    """Return Mismatches for *f90_path*'s driver program(s).

    Empty both when everything matches AND when the file has no
    ``program ... end program`` block at all, or that block declares
    neither ``errmsg`` nor ``errflg`` -- this tool only checks drivers that
    actually declare the conventional locals, matching the one real failure
    mode found in this repo (not every program calls into a generated cap).
    """
    from xdsl_ccpp.transforms.fparser2_to_meta import extract_program_locals

    with open(f90_path) as f:
        source = f.read()

    programs = extract_program_locals(source, f90_path, names=_CHECKED_NAMES)

    mismatches: list[Mismatch] = []
    for program_name, args in programs:
        if not args:
            continue
        mismatches.extend(
            compare_arg_tables(_expected_table(program_name), _actual_table(program_name, args))
        )
    return mismatches


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Check a host-driver program's own errmsg/errflg locals against "
            "the CCPP protocol's fixed convention (character(len=512) / "
            "integer), independent of any .meta file."
        )
    )
    parser.add_argument("f90_files", nargs="+", metavar="FILE.F90")
    args = parser.parse_args()

    if not _fparser_available():
        print(
            "Error: fparser is not installed.\n  Install via:  pip install fparser",
            file=sys.stderr,
        )
        sys.exit(1)

    any_errors = False
    for f90_file in args.f90_files:
        try:
            mismatches = check_driver_file(f90_file)
        except Exception as exc:
            print(f"Error: failed to parse '{f90_file}': {exc}", file=sys.stderr)
            any_errors = True
            continue

        if mismatches:
            any_errors = True
            print(f"'{f90_file}':")
            for m in mismatches:
                print(str(m))

    sys.exit(1 if any_errors else 0)


if __name__ == "__main__":
    main()
