"""Unit tests for ccpp_track_variables.

Tests cover the core tracking logic (track(), _find_variable(), etc.)
both with minimal inline meta content and with the real example files.
"""

import pathlib

import pytest

from xdsl.dialects.builtin import ModuleOp

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.tools.ccpp_track_variables import (
    TrackResult,
    _build_host_unit_map,
    _find_partial_matches,
    _find_variable,
    _index_scheme_arg_tables,
    _load_module,
    track,
)

# ── Paths to the example directories ─────────────────────────────────────────

_HERE = pathlib.Path(__file__).parent
_EXAMPLES = _HERE.parent.parent / "examples"
_ADV = _EXAMPLES / "advection"
_CAP = _EXAMPLES / "capgen"


# ── Inline meta helpers ───────────────────────────────────────────────────────

def _scheme_meta(name: str, extra_args: str = "") -> str:
    return f"""\
[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_run
  type = scheme
{extra_args}
{CCPP_MANDATORY_ARGS}
"""


def _host_meta(name: str, vars_content: str) -> str:
    return f"""\
[ccpp-table-properties]
  name = {name}
  type = module
[ccpp-arg-table]
  name = {name}
  type = module
{vars_content}
"""


# ── Tests for helper functions ────────────────────────────────────────────────

class TestFindVariable:
    """Tests for _find_variable() in isolation."""

    def test_finds_matching_variable(self, build_module):
        scheme_content = _scheme_meta("my_scheme", """\
[ ps ]
  standard_name = surface_air_pressure
  type = real
  kind = kind_phys
  intent = in
  dimensions = (horizontal_loop_extent)
  units = hPa
""")
        host_content = _host_meta("host_mod", """\
[ phost ]
  standard_name = surface_air_pressure
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  units = Pa
""")
        module = build_module([scheme_content], [host_content])
        tables = _index_scheme_arg_tables(module)
        host_map = _build_host_unit_map(module)

        tbl = tables["my_scheme_run"]
        result = _find_variable(tbl, "surface_air_pressure", host_map)

        assert result is not None
        local_name, intent, scheme_u, host_u, mismatch = result
        assert local_name == "ps"
        assert intent == "in"
        assert scheme_u == "hpa"
        assert host_u == "pa"
        assert mismatch is True

    def test_returns_none_when_not_found(self, build_module):
        scheme_content = _scheme_meta("my_scheme")
        module = build_module([scheme_content], [])
        tables = _index_scheme_arg_tables(module)
        tbl = tables["my_scheme_run"]
        result = _find_variable(tbl, "nonexistent_variable", {})
        assert result is None

    def test_no_mismatch_when_units_match(self, build_module):
        scheme_content = _scheme_meta("my_scheme", """\
[ temp ]
  standard_name = air_temperature
  type = real
  kind = kind_phys
  intent = inout
  dimensions = (horizontal_loop_extent)
  units = K
""")
        host_content = _host_meta("host_mod", """\
[ T ]
  standard_name = air_temperature
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  units = K
""")
        module = build_module([scheme_content], [host_content])
        tables = _index_scheme_arg_tables(module)
        host_map = _build_host_unit_map(module)

        result = _find_variable(tables["my_scheme_run"], "air_temperature", host_map)
        assert result is not None
        _, _, _, _, mismatch = result
        assert mismatch is False

    def test_no_mismatch_for_dimensionless_units(self, build_module):
        scheme_content = _scheme_meta("my_scheme", """\
[ flag ]
  standard_name = some_flag
  type = integer
  intent = in
  dimensions = ()
  units = 1
""")
        host_content = _host_meta("host_mod", """\
[ flag_host ]
  standard_name = some_flag
  type = integer
  dimensions = ()
  units = none
""")
        module = build_module([scheme_content], [host_content])
        tables = _index_scheme_arg_tables(module)
        host_map = _build_host_unit_map(module)

        result = _find_variable(tables["my_scheme_run"], "some_flag", host_map)
        assert result is not None
        _, _, _, _, mismatch = result
        assert mismatch is False


class TestFindPartialMatches:
    """Tests for _find_partial_matches()."""

    def test_finds_partial_match(self, build_module):
        scheme_content = _scheme_meta("my_scheme", """\
[ temp_lay ]
  standard_name = air_temperature_at_layer_midpoint
  type = real
  kind = kind_phys
  intent = in
  dimensions = (horizontal_loop_extent)
  units = K
""")
        module = build_module([scheme_content], [])
        tables = _index_scheme_arg_tables(module)
        matches = _find_partial_matches(tables["my_scheme_run"], "air_temperature")
        assert "air_temperature_at_layer_midpoint" in matches

    def test_no_partial_match_on_exact(self, build_module):
        scheme_content = _scheme_meta("my_scheme", """\
[ temp ]
  standard_name = air_temperature
  type = real
  kind = kind_phys
  intent = in
  dimensions = ()
  units = K
""")
        module = build_module([scheme_content], [])
        tables = _index_scheme_arg_tables(module)
        # Exact match should NOT appear in partial matches
        matches = _find_partial_matches(tables["my_scheme_run"], "air_temperature")
        assert "air_temperature" not in matches


# ── Tests for the track() function ───────────────────────────────────────────

class TestTrack:
    """Tests for the top-level track() function."""

    def _two_scheme_module(self, build_module):
        scheme_a = _scheme_meta("scheme_a", """\
[ ps ]
  standard_name = surface_air_pressure
  type = real
  kind = kind_phys
  intent = in
  dimensions = (horizontal_loop_extent)
  units = hPa
""")
        scheme_b = _scheme_meta("scheme_b", """\
[ ps2 ]
  standard_name = surface_air_pressure
  type = real
  kind = kind_phys
  intent = inout
  dimensions = (horizontal_loop_extent)
  units = Pa
""")
        host_content = _host_meta("host_mod", """\
[ ps_host ]
  standard_name = surface_air_pressure
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  units = Pa
""")
        suite_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <scheme>scheme_a</scheme>
    <scheme>scheme_b</scheme>
  </group>
</suite>
"""
        return build_module([scheme_a, scheme_b], [host_content], suite_xml)

    def test_finds_variable_in_two_schemes(self, build_module):
        module = self._two_scheme_module(build_module)
        results, partial = track(module, "surface_air_pressure")

        assert len(results) == 2
        assert results[0].entry_point == "scheme_a_run"
        assert results[0].local_name == "ps"
        assert results[0].intent == "in"
        assert results[0].unit_mismatch is True

        assert results[1].entry_point == "scheme_b_run"
        assert results[1].local_name == "ps2"
        assert results[1].unit_mismatch is False

    def test_not_found_returns_empty_with_partial(self, build_module):
        scheme = _scheme_meta("scheme_a", """\
[ temp_lay ]
  standard_name = air_temperature_at_layer_midpoint
  type = real
  kind = kind_phys
  intent = in
  dimensions = (horizontal_loop_extent)
  units = K
""")
        suite_xml = minimal_suite_xml("scheme_a")
        module = build_module([scheme], [], suite_xml)
        results, partial = track(module, "air_temperature")

        assert results == []
        assert "air_temperature_at_layer_midpoint" in partial

    def test_suite_filter(self, build_module):
        module = self._two_scheme_module(build_module)
        results, _ = track(module, "surface_air_pressure", suite_filter="other_suite")
        assert results == []

    def test_case_insensitive(self, build_module):
        module = self._two_scheme_module(build_module)
        results_lower, _ = track(module, "surface_air_pressure")
        results_mixed, _ = track(module, "Surface_Air_Pressure")
        assert len(results_lower) == len(results_mixed)

    def test_result_fields(self, build_module):
        module = self._two_scheme_module(build_module)
        results, _ = track(module, "surface_air_pressure")
        r = results[0]
        assert r.suite_name == "test_suite"
        assert r.group_name == "physics"
        assert r.scheme_units == "hpa"
        assert r.host_units == "pa"


# ── Integration tests against real example files ─────────────────────────────

class TestAdvectionIntegration:
    """Track surface_air_pressure through the advection cld_suite."""

    @pytest.fixture(scope="class")
    def adv_module(self):
        suites = [str(_ADV / "cld_suite.xml")]
        scheme_files = [
            str(_ADV / "const_indices.meta"),
            str(_ADV / "cld_liq.meta"),
            str(_ADV / "apply_constituent_tendencies.meta"),
            str(_ADV / "cld_ice.meta"),
        ]
        host_files = [str(_ADV / "test_host_data.meta")]
        return _load_module(suites, scheme_files, host_files)

    def test_found_in_cld_liq_and_cld_ice(self, adv_module):
        results, _ = track(adv_module, "surface_air_pressure")
        entry_points = [r.entry_point for r in results]
        assert "cld_liq_run" in entry_points
        assert "cld_ice_run" in entry_points

    def test_cld_liq_has_unit_mismatch(self, adv_module):
        results, _ = track(adv_module, "surface_air_pressure")
        liq = next(r for r in results if r.entry_point == "cld_liq_run")
        assert liq.local_name == "ps"
        assert liq.intent == "in"
        assert liq.scheme_units == "hpa"
        assert liq.host_units == "pa"
        assert liq.unit_mismatch is True

    def test_cld_ice_no_unit_mismatch(self, adv_module):
        results, _ = track(adv_module, "surface_air_pressure")
        ice = next(r for r in results if r.entry_point == "cld_ice_run")
        assert ice.local_name == "ps"
        assert ice.intent == "in"
        assert ice.scheme_units == "pa"
        assert ice.host_units == "pa"
        assert ice.unit_mismatch is False

    def test_not_found_returns_empty(self, adv_module):
        results, _ = track(adv_module, "nonexistent_variable_xyz")
        assert results == []

    def test_suite_name_in_results(self, adv_module):
        results, _ = track(adv_module, "surface_air_pressure")
        assert all(r.suite_name == "cld_suite" for r in results)


class TestCapgenIntegration:
    """Track surface_air_pressure through the capgen ddt_suite."""

    @pytest.fixture(scope="class")
    def cap_module(self):
        suites = [str(_CAP / "ddt_suite.xml")]
        scheme_files = [
            str(_CAP / "make_ddt.meta"),
            str(_CAP / "environ_conditions.meta"),
        ]
        host_files = [str(_CAP / "test_host_data.meta")]
        return _load_module(suites, scheme_files, host_files)

    def test_found_in_environ_conditions(self, cap_module):
        results, _ = track(cap_module, "surface_air_pressure")
        entry_points = [r.entry_point for r in results]
        assert "environ_conditions_run" in entry_points

    def test_environ_conditions_no_mismatch(self, cap_module):
        results, _ = track(cap_module, "surface_air_pressure")
        ec = next(r for r in results if r.entry_point == "environ_conditions_run")
        assert ec.local_name == "psurf"
        assert ec.intent == "in"
        assert ec.scheme_units == "pa"
        assert ec.host_units == "pa"
        assert ec.unit_mismatch is False
