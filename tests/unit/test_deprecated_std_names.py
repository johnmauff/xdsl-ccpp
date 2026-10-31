"""Unit tests for deprecated-standard_name rejection / --legacy-mode.

Backlog: after migrating every example off the legacy `horizontal_loop_extent`
convention (in favor of `horizontal_dimension`), the old name was first
flagged with a warning only (no rejection). Matching real capgen-v1's own
strict posture (and its own `--legacy-mode` flag), it is now rejected by
default; `--legacy-mode` (`set_legacy_mode`/`is_legacy_mode`, in
`ccpp_conventions.py`) downgrades this to the original warning and preserves
full support. `ArgumentOp.__init__` (`xdsl_ccpp/dialects/ccpp.py`) is the
single shared construction point used by every frontend (`ccpp_xml.py`,
`py_api.py`, `fparser2_to_meta.py`), so the check lives
there, backed by `ccpp_conventions.py`'s `CCPP_DEPRECATED_STD_NAMES` map /
`deprecated_std_name_warning`.
"""

import pytest

from xdsl_ccpp.dialects.ccpp import ArgumentOp
from xdsl_ccpp.util.ccpp_conventions import (
    deprecated_std_name_warning,
    is_legacy_mode,
    report_deprecated_uses,
    set_legacy_mode,
    set_verbosity,
    verbosity,
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

    def test_openmp_threads_legacy_name_returns_a_warning_mentioning_the_replacement(self):
        """task11-omp-thread item 1: number_of_openmp_threads -> number_of_threads,
        gated behind the same --legacy-mode shim, mirroring real capgen-v1's
        own legacy_compat.py mapping. A scalar count, not a dimension name --
        only ever appears as a bare standard_name, never inside dimensions=."""
        msg = deprecated_std_name_warning("number_of_openmp_threads")
        assert msg is not None
        assert "number_of_openmp_threads" in msg
        assert "number_of_threads" in msg

    def test_number_of_threads_itself_returns_none(self):
        assert deprecated_std_name_warning("number_of_threads") is None


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

    def test_bare_colon_dimension_is_preserved_not_emptied(self):
        # dup-meta-shadow-elim (BACKLOG.md), Phase 7: a bare ':' is a real,
        # different convention from range notation -- a deferred/assumed-
        # shape dimension with no standard name at all (confirmed real:
        # examples/advection's own cld_liq.meta/cld_ice.meta both declare a
        # constituent-properties array as `dimensions = (:)`). The range-
        # notation upper-bound split used to apply here too, silently
        # producing an EMPTY dim_names instead of preserving ':' -- found
        # via a real build failure when examples/advection_nometa's
        # generated .meta fell back to a stub dimension name for this
        # exact case, which a real suite then counted as a bogus extra
        # host variable.
        op = ArgumentOp(
            "dyn_const", "ccpp_constituent_properties_t",
            {"type": "ccpp_constituent_properties_t",
             "standard_name": "dynamic_constituents_for_cld_liq",
             "dimensions": "(:)", "intent": "out"},
        )
        assert op.dim_names.data == ":"

    def test_current_convention_is_silent(self, capsys):
        ArgumentOp(
            "ncol", "integer",
            {"type": "integer", "standard_name": "horizontal_dimension",
             "dimensions": "()", "intent": "in"},
        )
        err = capsys.readouterr().err
        assert err == ""

    def test_openmp_threads_current_convention_is_silent(self, capsys):
        ArgumentOp(
            "nthreads", "integer",
            {"type": "integer", "standard_name": "number_of_threads",
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

    def test_openmp_threads_scalar_standard_name_raises(self):
        with pytest.raises(ValueError, match="number_of_openmp_threads"):
            ArgumentOp(
                "nthreads", "integer",
                {"type": "integer", "standard_name": "number_of_openmp_threads",
                 "dimensions": "()", "intent": "in"},
            )


class TestArgumentOpAcceptsUnderLegacyMode:
    """With --legacy-mode on, the legacy name must still parse successfully
    (a warning, not a rejection) -- the original, pre-default-flip behavior.
    The warning is recorded when the op is built and printed by
    report_deprecated_uses (the frontend calls it once)."""

    @pytest.fixture(autouse=True)
    def _legacy_mode(self):
        # The report prints at the process's verbosity, which another test's
        # ccppMain().run(verbose=0) may have left at 0.
        previous = verbosity()
        set_legacy_mode(True)
        set_verbosity(1)
        yield
        set_legacy_mode(False)
        set_verbosity(previous)

    def test_is_legacy_mode_reports_enabled(self):
        assert is_legacy_mode() is True

    def test_scalar_standard_name_warns(self, capsys):
        ArgumentOp(
            "ncol", "integer",
            {"type": "integer", "standard_name": "horizontal_loop_extent",
             "dimensions": "()", "intent": "in"},
        )
        report_deprecated_uses()  # recorded at construction, reported once
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
        report_deprecated_uses()  # recorded at construction, reported once
        err = capsys.readouterr().err
        assert "horizontal_loop_extent" in err

    def test_range_notation_dim_name_warns(self, capsys):
        ArgumentOp(
            "temp_level", "real",
            {"type": "real", "standard_name": "potential_temperature_at_interface",
             "dimensions": "(ccpp_constant_one:horizontal_loop_extent, vertical_interface_dimension)",
             "intent": "inout"},
        )
        report_deprecated_uses()  # recorded at construction, reported once
        err = capsys.readouterr().err
        assert "horizontal_loop_extent" in err

    def test_openmp_threads_scalar_standard_name_warns(self, capsys):
        ArgumentOp(
            "nthreads", "integer",
            {"type": "integer", "standard_name": "number_of_openmp_threads",
             "dimensions": "()", "intent": "in"},
        )
        report_deprecated_uses()  # recorded at construction, reported once
        err = capsys.readouterr().err
        assert "number_of_openmp_threads" in err
        assert "number_of_threads" in err

    def test_current_convention_is_silent(self, capsys):
        ArgumentOp(
            "ncol", "integer",
            {"type": "integer", "standard_name": "horizontal_dimension",
             "dimensions": "()", "intent": "in"},
        )
        err = capsys.readouterr().err
        assert err == ""
