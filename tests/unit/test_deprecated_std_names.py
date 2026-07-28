"""Unit tests for deprecated-standard_name warnings.

Backlog: after migrating every example off the legacy `horizontal_loop_extent`
convention (in favor of `horizontal_dimension`), the user asked to flag the
old name as no-longer-supported without breaking anything still using it --
a warning, not a rejection. `ArgumentOp.__init__` (`xdsl_ccpp/dialects/ccpp.py`)
is the single shared construction point used by every frontend (`ccpp_xml.py`,
`py_api.py`, `fir_to_meta.py`, `fparser2_to_meta.py`), so the check lives
there, backed by `ccpp_conventions.py`'s `CCPP_DEPRECATED_STD_NAMES` map /
`deprecated_std_name_warning`.
"""

import pytest

from xdsl_ccpp.dialects.ccpp import ArgumentOp
from xdsl_ccpp.util.ccpp_conventions import deprecated_std_name_warning


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


class TestArgumentOpEmitsWarningNotRejection:
    """The legacy name must still parse successfully (warning, not an error) --
    ArgumentOp construction must not raise for either case."""

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
        """'ccpp_constant_one:horizontal_loop_extent' takes the upper bound
        (the existing dimensions-parsing convention) -- still flagged."""
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

    def test_no_warning_construction_does_not_crash(self):
        """Sanity check: an entirely unrelated arg must not warn or raise."""
        ArgumentOp(
            "errflg", "integer",
            {"type": "integer", "standard_name": "ccpp_error_code",
             "dimensions": "()", "intent": "out"},
        )
