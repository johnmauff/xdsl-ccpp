"""--legacy-mode warnings: ArgumentOp records each deprecated standard name
and the frontend reports them once, at its --verbose level."""

import pytest

from xdsl_ccpp.dialects.ccpp import ArgumentOp
from xdsl_ccpp.util import ccpp_conventions as cc


@pytest.fixture
def legacy(legacy_mode, monkeypatch):
    monkeypatch.setattr(cc, "_DEPRECATED_USES", [])
    monkeypatch.setattr(cc, "_VERBOSITY", 1)


def _arg(name, std_name="horizontal_loop_extent", dims="()"):
    return ArgumentOp(name, "integer", {
        "type": "integer", "standard_name": std_name, "dimensions": dims,
        "intent": "in",
    })


def _uses(capsys):
    with cc.deprecation_source("a.meta"):
        _arg("ncol")
        _arg("t", std_name="air_temperature", dims="(horizontal_loop_extent)")
    with cc.deprecation_source("b.meta"):
        _arg("ncol")
        _arg("ncol")
    assert capsys.readouterr().err == ""  # recorded, not printed


def test_level_1_prints_one_line_per_name(legacy, capsys):
    _uses(capsys)
    cc.report_deprecated_uses()
    assert capsys.readouterr().err.splitlines() == [
        "Warning(LEGACY): standard_name 'horizontal_loop_extent' is deprecated -- "
        "use 'horizontal_dimension' instead (4 uses in 2 .meta files; "
        "--verbose 2 lists them)"
    ]


def test_level_2_lists_arguments_by_file(legacy, capsys):
    _uses(capsys)
    cc.set_verbosity(2)
    cc.report_deprecated_uses()
    assert capsys.readouterr().err.splitlines()[1:] == [
        "  a.meta: ncol, t",
        "  b.meta: ncol (x2)",
    ]


def test_level_0_prints_nothing_and_report_forgets(legacy, capsys):
    _uses(capsys)
    cc.set_verbosity(0)
    cc.report_deprecated_uses()
    cc.set_verbosity(1)
    cc.report_deprecated_uses()
    assert capsys.readouterr().err == ""


def test_discarded_records_are_not_reported(legacy, capsys):
    with cc.deprecation_records_discarded():
        _uses(capsys)
    cc.report_deprecated_uses()
    assert capsys.readouterr().err == ""


def test_without_legacy_mode_still_an_error():
    with pytest.raises(ValueError, match="--legacy-mode"):
        _arg("ncol")
