"""Checks for optional dependencies, importable without them."""


def fparser_available() -> bool:
    """True if fparser (the `validate` extra) is installed."""
    try:
        import fparser.two.Fortran2003  # noqa: F401
        return True
    except ImportError:
        return False
