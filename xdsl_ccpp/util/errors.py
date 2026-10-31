"""Messages for the user: errors in the generator's input (reported without
a Python traceback) and warnings."""

import sys

from xdsl_ccpp.util.ccpp_conventions import verbosity


class CcppInputError(ValueError):
    """An error in the generator's input -- suite XML, .meta files, scheme or
    host sources -- as opposed to a generator bug. Entry points print it as
    ``Error: <message>`` and exit with status 1 (report_input_errors);
    ``--verbose 2`` shows the traceback instead. A ValueError, so handlers
    and tests that expect ValueError still catch it."""


def report_input_errors(main):
    """Run *main()*; print a CcppInputError as a plain error and exit 1."""
    try:
        return main()
    except CcppInputError as exc:
        if verbosity() >= 2:
            raise
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


_WARNED: set[str] = set()


def warn_once(message: str) -> None:
    """Print ``Warning: <message>`` to stderr, once per process for the same
    message: several generation phases can report the same problem."""
    if message not in _WARNED:
        _WARNED.add(message)
        print(f"Warning: {message}", file=sys.stderr)
