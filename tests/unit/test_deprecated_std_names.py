"""Unit tests for deprecated-standard_name rejection / --legacy-mode.

Backlog: after migrating every example off the legacy `horizontal_loop_extent`
convention (in favor of `horizontal_dimension`), the old name was first
flagged with a warning only (no rejection). Matching real capgen-v1's own
strict posture (and its own `--legacy-mode` flag), it is now rejected by
default; `--legacy-mode` (`set_legacy_mode`/`is_legacy_mode`, in
`ccpp_conventions.py`) downgrades this to the original warning and preserves
full support. `ArgumentOp.__init__` (`xdsl_ccpp/dialects/ccpp.py`) is the
single shared construction point used by every frontend (`ccpp_xml.py`,
`py_api.py`, `fir_to_meta.py`, `fparser2_to_meta.py`), so the check lives
there, backed by `ccpp_conventions.py`'s `CCPP_DEPRECATED_STD_NAMES` map /
`deprecated_std_name_warning`.
"""

import pytest

from xdsl_ccpp.dialects.ccpp import ArgumentOp
from xdsl_ccpp.util.ccpp_conventions import (
    deprecated_std_name_warning,
    is_legacy_mode,
    set_legacy_mode,
)


class TestDeprecatedStdNameWarning:
    """deprecated_std_name_warning itself: the pure lookup used by ArgumentOp."""

    def test_legacy_name_returns_a_warning_mentioning_the_replacement(self):
        msg = deprecated_std_name_warning("horizontal_loop_extent")
        assert msg is not None
        assert "horizontal_loop_extent" in msg
        assert "horizontal_dimension" in msg

    def test_legacy_name_is_case_insensitive(self):
        assert deprecated_std_name_warning("Horizontal_Loop_Extent") is not None

    def test_current_convention_name_returns_none(self):
        assert deprecated_std_name_warning("horizontal_dimension") is None

    def test_unrelated_name_returns_none(self):
        assert deprecated_std_name_warning("air_temperature") is None


class TestArgumentOpRejectsByDefault:
    """Without --legacy-mode, a deprecated standard_name must raise, whether
    declared as the arg's own standard_name or as one of its dimension names."""

    def test_scalar_standard_name_raises(self):
        with pytest.raises(ValueError, match="horizontal_loop_extent"):
            ArgumentOp(
                "ncol", "integer",
                {"type": "integer", "standard_name": "horizontal_loop_extent",
                 "dimensions": "()", "intent": "in"},
            )

    def test_array_dim_name_raises(self):
        with pytest.raises(ValueError, match="horizontal_loop_extent"):
            ArgumentOp(
                "temp", "real",
                {"type": "real", "standard_name": "air_temperature",
                 "dimensions": "(horizontal_loop_extent, vertical_layer_dimension)",
                 "intent": "inout"},
            )

    def test_range_notation_dim_name_raises(self):
        """'ccpp_constant_one:horizontal_loop_extent' takes the upper bound
        (the existing dimensions-parsing convention) -- still flagged."""
        with pytest.raises(ValueError, match="horizontal_loop_extent"):
            ArgumentOp(
                "temp_level", "real",
                {"type": "real", "standard_name": "potential_temperature_at_interface",
                 "dimensions": "(ccpp_constant_one:horizontal_loop_extent, vertical_interface_dimension)",
                 "intent": "inout"},
            )

    def test_current_convention_is_silent(self, capsys):
        ArgumentOp(
            "ncol", "integer",
            {"type": "integer", "standard_name": "horizontal_dimension",
             "dimensions": "()", "intent": "in"},
        )
        err = capsys.readouterr().err
        assert err == ""

    def test_no_warning_construction_does_not_crash(self):
        """Sanity check: an entirely unrelated arg must not warn or raise."""
        ArgumentOp(
            "errflg", "integer",
            {"type": "integer", "standard_name": "ccpp_error_code",
             "dimensions": "()", "intent": "out"},
        )


class TestArgumentOpAcceptsUnderLegacyMode:
    """With --legacy-mode on, the legacy name must still parse successfully
    (a warning, not a rejection) -- the original, pre-default-flip behavior."""

    @pytest.fixture(autouse=True)
    def _legacy_mode(self):
        set_legacy_mode(True)
        yield
        set_legacy_mode(False)

    def test_is_legacy_mode_reports_enabled(self):
        assert is_legacy_mode() is True

    def test_scalar_standard_name_warns(self, capsys):
        ArgumentOp(
            "ncol", "integer",
            {"type": "integer", "standard_name": "horizontal_loop_extent",
             "dimensions": "()", "intent": "in"},
        )
        err = capsys.readouterr().err
        assert "horizontal_loop_extent" in err
        assert "horizontal_dimension" in err

    def test_array_dim_name_warns(self, capsys):
        ArgumentOp(
            "temp", "real",
            {"type": "real", "standard_name": "air_temperature",
             "dimensions": "(horizontal_loop_extent, vertical_layer_dimension)",
             "intent": "inout"},
        )
        err = capsys.readouterr().err
        assert "horizontal_loop_extent" in err

    def test_range_notation_dim_name_warns(self, capsys):
        ArgumentOp(
            "temp_level", "real",
            {"type": "real", "standard_name": "potential_temperature_at_interface",
             "dimensions": "(ccpp_constant_one:horizontal_loop_extent, vertical_interface_dimension)",
             "intent": "inout"},
        )
        err = capsys.readouterr().err
        assert "horizontal_loop_extent" in err

    def test_current_convention_is_silent(self, capsys):
        ArgumentOp(
            "ncol", "integer",
            {"type": "integer", "standard_name": "horizontal_dimension",
             "dimensions": "()", "intent": "in"},
        )
        err = capsys.readouterr().err
        assert err == ""
