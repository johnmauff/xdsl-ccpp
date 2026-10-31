"""report_input_errors: an error in the input is printed as a plain
'Error:' line (traceback only at --verbose 2); other exceptions keep their
traceback."""

import pytest

from xdsl_ccpp.util import ccpp_conventions as cc
from xdsl_ccpp.util.errors import CcppInputError, report_input_errors


def _fail(exc):
    def main():
        raise exc
    return main


def test_input_error_is_a_plain_error(monkeypatch, capsys):
    monkeypatch.setattr(cc, "_VERBOSITY", 1)
    with pytest.raises(SystemExit) as exit_info:
        report_input_errors(_fail(CcppInputError("arg 'x' has no host match")))
    assert exit_info.value.code == 1
    assert capsys.readouterr().err == "Error: arg 'x' has no host match\n"


def test_verbose_2_keeps_the_traceback(monkeypatch):
    monkeypatch.setattr(cc, "_VERBOSITY", 2)
    with pytest.raises(CcppInputError):
        report_input_errors(_fail(CcppInputError("bad input")))


def test_other_errors_are_not_caught(monkeypatch):
    monkeypatch.setattr(cc, "_VERBOSITY", 1)
    with pytest.raises(ValueError, match="internal"):
        report_input_errors(_fail(ValueError("internal invariant")))


def test_input_error_is_a_value_error():
    assert issubclass(CcppInputError, ValueError)
