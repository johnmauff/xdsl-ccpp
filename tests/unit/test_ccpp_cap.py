"""Unit tests for xdsl_ccpp.transforms.ccpp_cap's pure-data functions.

Phase 4 (narrow extraction): _build_cap_var_map was extracted from an inline
block in _generate_ccpp_cap_module into a named, independently-testable
function. This is its first direct unit test -- previously only exercised
indirectly via end-to-end examples.
"""

from xdsl_ccpp.transforms.ccpp_cap import _build_cap_var_map
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    CCPPArgument,
    CCPPArgumentTable,
    CCPPTableProperties,
    XMLGroup,
    XMLScheme,
    XMLSuite,
)


def _make_arg(name, **attrs):
    arg = CCPPArgument(name)
    for k, v in attrs.items():
        arg.setAttr(k, v)
    return arg


def _make_arg_table(name, args, table_type):
    tbl = CCPPArgumentTable()
    tbl.setAttr("name", name)
    tbl.setAttr("type", table_type)
    for arg in args:
        tbl.setFunctionArgument(arg)
    return tbl


def _make_table_props(name, type_, arg_table):
    props = CCPPTableProperties()
    props.setAttr("name", name)
    props.setAttr("type", type_)
    props.arg_tables[name] = arg_table
    return props


class TestBuildCapVarMap:
    """_build_cap_var_map classifies unresolved suite-cap-signature args into
    framework arrays, scratch vars, or leaves them alone (host-matched)."""

    def _meta_data(self):
        # phys_scheme's _run table declares 4 args covering each outcome:
        # a framework array, a plain scratch var, a host-matched var
        # (excluded), and a constituent-tendency scratch var.
        scheme_props = _make_table_props(
            "phys_scheme", "scheme",
            _make_arg_table("phys_scheme_run", [
                _make_arg("cnst", standard_name="ccpp_constituents"),
                _make_arg("scratch1", standard_name="some_scratch_quantity"),
                _make_arg(
                    "matched1", standard_name="matched_quantity",
                    model_var_name="host_var",
                ),
                _make_arg(
                    "tend1", standard_name="tendency_of_water_vapor",
                    constituent=True,
                ),
            ], "scheme"),
        )
        scheme_props.arg_tables["phys_scheme_run"] = scheme_props.arg_tables.pop(
            "phys_scheme"
        )
        return {"phys_scheme": scheme_props}

    def _suite_descriptions(self):
        suite = XMLSuite("testsuite", "1")
        group = XMLGroup("run")
        group.addChild(XMLScheme("phys_scheme"))
        suite.addChild(group)
        return {"testsuite": suite}

    def _public_fns(self):
        callee_input_names = ["cnst", "scratch1", "matched1", "tend1"]
        return {
            "testsuite_suite_run": (
                "testsuite_cap_mod",
                [],
                [None] * len(callee_input_names),
                callee_input_names,
            ),
        }

    def _build(self):
        return _build_cap_var_map(
            self._meta_data(), self._suite_descriptions(), self._public_fns()
        )

    def test_framework_array_maps_to_known_cap_var(self):
        cap_var_map, _host_var_map_lc, _scratch = self._build()
        assert cap_var_map["ccpp_constituents"] == ("lc_constituent_array", None, None)

    def test_unmatched_scratch_var_becomes_cap_owned(self):
        cap_var_map, _host_var_map_lc, scratch_var_list = self._build()
        assert cap_var_map["some_scratch_quantity"] == ("lc_scratch1", None, None)
        assert ("lc_scratch1", 0, "ncols, pver", None) in scratch_var_list

    def test_host_matched_arg_is_excluded(self):
        cap_var_map, _host_var_map_lc, scratch_var_list = self._build()
        assert "matched_quantity" not in cap_var_map
        assert not any(entry[0] == "lc_matched1" for entry in scratch_var_list)

    def test_constituent_tendency_scratch_var_records_const_std_name(self):
        cap_var_map, _host_var_map_lc, scratch_var_list = self._build()
        assert cap_var_map["tendency_of_water_vapor"] == ("lc_tend1", None, None)
        assert ("lc_tend1", 0, "ncols, pver", "water_vapor") in scratch_var_list

    def test_host_var_map_lc_empty_when_no_module_tables(self):
        _cap_var_map, host_var_map_lc, _scratch = self._build()
        assert host_var_map_lc == {}
