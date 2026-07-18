"""Unit tests for run_dispatch.py's pure-data functions.

Phase 3a (the mechanical move of the run-dispatch cluster out of ccpp_cap.py)
made it possible, for the first time, to unit-test this logic in isolation
instead of only exercising it indirectly through full end-to-end pipeline
runs. These tests cover the three functions that operate on plain data
(dicts, descriptor objects, strings) rather than live xDSL IR/Block objects:

  - _resolve_ddt_access_path   -- recursive DDT type -> Fortran accessor path
  - _resolve_member_subscripts -- standard_name token rewriting in subscripts
  - _build_run_metadata_maps   -- host/DDT/constituent lookup maps from meta_data

The remaining, IR-heavy functions in this module (_build_per_suite_run_info,
_build_run_block_signature, _build_run_chain_preamble, _build_run_dispatch_chain,
_assemble_run_fn, _generate_run_fn, _generate_suite_part_list_fn) still rely on
the existing end-to-end example suites for coverage -- constructing valid
Block/FuncOp fixtures by hand for those is a separate, larger effort.
"""

from xdsl_ccpp.transforms.run_dispatch import (
    _build_run_metadata_maps,
    _resolve_ddt_access_path,
    _resolve_member_subscripts,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    CCPPArgument,
    CCPPArgumentTable,
    CCPPTableProperties,
)


# ---------------------------------------------------------------------------
# Helpers to build minimal meta_data dicts (same convention as
# test_chost_ddt_expand.py / test_chost_ddt_error.py)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# _resolve_ddt_access_path
# ---------------------------------------------------------------------------

class TestResolveDDTAccessPath:
    """_resolve_ddt_access_path resolves a DDT type name to its Fortran accessor."""

    def test_direct_module_level_instance(self):
        """A type with a direct module-level instance resolves with an empty prefix."""
        ddt_instance_map = {"phys_state_t": ("phys_state", "test_host_mod")}
        ddt_parent_map = {}
        result = _resolve_ddt_access_path("phys_state_t", ddt_instance_map, ddt_parent_map)
        assert result == ("phys_state", "test_host_mod", "")

    def test_one_level_nested_ddt(self):
        """A type nested one level inside a module-level instance builds a '%'-prefix."""
        # rad_t is a member "rad" of phys_state_t, which has a module-level instance.
        ddt_instance_map = {"phys_state_t": ("phys_state", "test_host_mod")}
        ddt_parent_map = {"rad_t": [("rad", "phys_state_t")]}
        result = _resolve_ddt_access_path("rad_t", ddt_instance_map, ddt_parent_map)
        assert result == ("phys_state", "test_host_mod", "rad%")

    def test_two_level_nested_ddt(self):
        """Two levels of nesting concatenate the path prefix in outer-to-inner order."""
        # temp_t is a member "temp_field" of rad_t, which is a member "rad" of
        # phys_state_t, which has a module-level instance.
        ddt_instance_map = {"phys_state_t": ("phys_state", "test_host_mod")}
        ddt_parent_map = {
            "rad_t": [("rad", "phys_state_t")],
            "temp_t": [("temp_field", "rad_t")],
        }
        result = _resolve_ddt_access_path("temp_t", ddt_instance_map, ddt_parent_map)
        assert result == ("phys_state", "test_host_mod", "rad%temp_field%")

    def test_unreachable_type_returns_none(self):
        """A type with no module-level instance anywhere in its ancestry returns None."""
        ddt_instance_map = {"phys_state_t": ("phys_state", "test_host_mod")}
        ddt_parent_map = {}  # orphan_t has no parent entry and no direct instance
        result = _resolve_ddt_access_path("orphan_t", ddt_instance_map, ddt_parent_map)
        assert result is None

    def test_circular_parent_chain_terminates(self):
        """A circular DDT parent chain hits the depth guard and returns None
        instead of recursing forever."""
        ddt_instance_map = {}  # no reachable instance at all
        ddt_parent_map = {
            "a_t": [("b_member", "b_t")],
            "b_t": [("a_member", "a_t")],  # a_t -> b_t -> a_t -> ... forever
        }
        result = _resolve_ddt_access_path("a_t", ddt_instance_map, ddt_parent_map)
        assert result is None

    def test_multiple_parent_candidates_tries_each(self):
        """When a type has more than one parent-member entry, each is tried in
        order until one resolves."""
        ddt_instance_map = {"phys_state_t": ("phys_state", "test_host_mod")}
        # rad_t is (spuriously) listed as a member of both an unreachable type
        # and phys_state_t; the unreachable candidate is tried first and
        # fails, so resolution falls through to the second candidate.
        ddt_parent_map = {
            "rad_t": [
                ("rad_a", "orphan_t"),
                ("rad_b", "phys_state_t"),
            ],
        }
        result = _resolve_ddt_access_path("rad_t", ddt_instance_map, ddt_parent_map)
        assert result == ("phys_state", "test_host_mod", "rad_b%")


# ---------------------------------------------------------------------------
# _resolve_member_subscripts
# ---------------------------------------------------------------------------

class TestResolveMemberSubscripts:
    """_resolve_member_subscripts rewrites standard_name subscript tokens to local names."""

    def test_no_parens_passes_through_unchanged(self):
        """A bare member name with no subscript is returned unchanged, with no sub_vars."""
        result, sub_vars = _resolve_member_subscripts("temp", {})
        assert result == "temp"
        assert sub_vars == []

    def test_bare_colons_pass_through(self):
        """Bare ':' tokens in the subscript are preserved as-is."""
        result, sub_vars = _resolve_member_subscripts("q(:,:)", {})
        assert result == "q(:, :)"
        assert sub_vars == []

    def test_integer_literal_passes_through(self):
        """Integer literal subscripts are preserved as-is."""
        result, sub_vars = _resolve_member_subscripts("q(:,1)", {})
        assert result == "q(:, 1)"
        assert sub_vars == []

    def test_standard_name_token_resolved_to_local_var(self):
        """A standard_name token in the subscript resolves to its local var name."""
        host_var_map = {
            "index_of_water_vapor_specific_humidity": ("index_qv", "test_host_mod"),
        }
        result, sub_vars = _resolve_member_subscripts(
            "q(:,:,index_of_water_vapor_specific_humidity)", host_var_map
        )
        assert result == "q(:, :, index_qv)"
        assert sub_vars == [("index_qv", "test_host_mod")]

    def test_unresolved_token_passes_through_unchanged(self):
        """A subscript token not present in host_var_map is left as written."""
        result, sub_vars = _resolve_member_subscripts("q(:,unknown_token)", {})
        assert result == "q(:, unknown_token)"
        assert sub_vars == []

    def test_case_insensitive_lookup(self):
        """host_var_map lookup is case-insensitive (token is lowercased before lookup)."""
        host_var_map = {"some_standard_name": ("local_var", "some_mod")}
        result, sub_vars = _resolve_member_subscripts("arr(SOME_STANDARD_NAME)", host_var_map)
        assert result == "arr(local_var)"
        assert sub_vars == [("local_var", "some_mod")]


# ---------------------------------------------------------------------------
# _build_run_metadata_maps
# ---------------------------------------------------------------------------

class TestBuildRunMetadataMaps:
    """_build_run_metadata_maps builds host/DDT/constituent lookup structures from meta_data."""

    def _meta_data(self):
        # A HOST table declaring a block-caller arg, surface_air_pressure.
        host_props = _make_table_props(
            "test_host", "host",
            _make_arg_table("test_host", [
                _make_arg("psurf", standard_name="surface_air_pressure"),
            ], "host"),
        )

        # A MODULE table declaring a scalar (with standard_name, so it lands
        # in host_var_map) and a DDT instance (phys_state, no standard_name).
        mod_props = _make_table_props(
            "test_host_mod", "module",
            _make_arg_table("test_host_mod", [
                _make_arg("nlev", standard_name="vertical_layer_dimension"),
                _make_arg("phys_state", type="phys_state_t"),
            ], "module"),
        )

        # A DDT table (phys_state_t) with a plain (non-DDT-typed) member.
        ddt_props = _make_table_props(
            "phys_state_t", "ddt",
            _make_arg_table("phys_state_t", [
                _make_arg("temp", standard_name="air_temperature"),
            ], "ddt"),
        )

        # A SCHEME table with a constituent-flagged arg in its _run table.
        scheme_props = _make_table_props(
            "cld_ice", "scheme",
            _make_arg_table("cld_ice_run", [
                _make_arg(
                    "dq",
                    standard_name="tendency_of_cloud_ice_mixing_ratio",
                    constituent=True,
                ),
            ], "scheme"),
        )
        # _make_table_props keys arg_tables by the *table* name; the scheme's
        # _run table is named "cld_ice_run", not "cld_ice" -- fix that up.
        scheme_props.arg_tables["cld_ice_run"] = scheme_props.arg_tables.pop("cld_ice")

        return {
            "test_host": host_props,
            "test_host_mod": mod_props,
            "phys_state_t": ddt_props,
            "cld_ice": scheme_props,
        }

    def test_host_var_map_from_module_tables_only(self):
        """host_var_map (include_host=False) collects standard_names from MODULE
        tables only -- HOST-table args like surface_air_pressure are excluded."""
        maps = _build_run_metadata_maps(self._meta_data())
        assert maps.host_var_map == {"vertical_layer_dimension": ("nlev", "test_host_mod")}

    def test_host_block_std_names_from_host_table(self):
        """host_block_std_names collects standard_names declared in HOST-type tables."""
        maps = _build_run_metadata_maps(self._meta_data())
        assert maps.host_block_std_names == {"surface_air_pressure"}

    def test_constituent_std_names_from_scheme_tables(self):
        """constituent_std_names collects standard_names of args flagged constituent."""
        maps = _build_run_metadata_maps(self._meta_data())
        assert maps.constituent_std_names == {"tendency_of_cloud_ice_mixing_ratio"}

    def test_ddt_type_names_collects_all_ddt_tables(self):
        """ddt_type_names is the set of all table names typed DDT."""
        maps = _build_run_metadata_maps(self._meta_data())
        assert maps.ddt_type_names == {"phys_state_t"}

    def test_ddt_instance_map_from_module_table(self):
        """ddt_instance_map maps a DDT type name to its (var_name, table_name) instance."""
        maps = _build_run_metadata_maps(self._meta_data())
        assert maps.ddt_instance_map == {"phys_state_t": ("phys_state", "test_host_mod")}

    def test_ddt_parent_map_empty_when_no_nested_ddts(self):
        """ddt_parent_map is empty when no DDT table has a member of another DDT type."""
        maps = _build_run_metadata_maps(self._meta_data())
        assert maps.ddt_parent_map == {}

    def test_ddt_parent_map_with_nested_ddt(self):
        """ddt_parent_map records a nested DDT member as (member_name, parent_table)."""
        meta_data = self._meta_data()
        # Add a second DDT, rad_t, and give phys_state_t a "rad" member of it.
        meta_data["rad_t"] = _make_table_props(
            "rad_t", "ddt",
            _make_arg_table("rad_t", [
                _make_arg("flux", standard_name="shortwave_flux"),
            ], "ddt"),
        )
        meta_data["phys_state_t"].arg_tables["phys_state_t"].setFunctionArgument(
            _make_arg("rad", type="rad_t")
        )

        maps = _build_run_metadata_maps(meta_data)
        assert maps.ddt_parent_map == {"rad_t": [("rad", "phys_state_t")]}
