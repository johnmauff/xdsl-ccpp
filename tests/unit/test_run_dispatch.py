"""Unit tests for run_dispatch.py's pure-data functions.

Phase 3a (the mechanical move of the run-dispatch cluster out of ccpp_cap.py)
made it possible, for the first time, to unit-test this logic in isolation
instead of only exercising it indirectly through full end-to-end pipeline
runs. These tests cover the functions that operate on plain data (dicts,
descriptor objects, strings) rather than live xDSL IR/Block objects:

  - _resolve_ddt_access_path   -- recursive DDT type -> Fortran accessor path
  - _resolve_member_subscripts -- standard_name token rewriting in subscripts
  - _build_run_metadata_maps   -- host/DDT/constituent lookup maps from meta_data
  - _build_per_suite_run_info  -- per-arg host/DDT/cap-var/block classification
                                   (needs a few llvm.GlobalOps but no Block/FuncOp
                                   fixture, so it's unit-testable too)

The remaining, IR-heavy functions in this module (_build_run_block_signature,
_build_run_chain_preamble, _build_run_dispatch_chain, _assemble_run_fn,
_generate_run_fn, _generate_suite_part_list_fn) still rely on the existing
end-to-end example suites for coverage -- constructing valid Block/FuncOp
fixtures by hand for those is a separate, larger effort.
"""

import pytest

from xdsl_ccpp.dialects.ccpp import ArgSourceKind
from xdsl_ccpp.transforms.run_dispatch import (
    _RunMetadataMaps,
    _build_per_suite_run_info,
    _build_resolved_arg_ops,
    _build_run_metadata_maps,
    _resolve_ddt_access_path,
    _resolve_member_subscripts,
    _resolved_arg_op_from_source,
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


# ---------------------------------------------------------------------------
# _build_per_suite_run_info -- physics_arg_sources / resolved_arg_ops parity
#
# Phase 3b Stage 2: resolved_arg_ops is a dual-build mirror of
# physics_arg_sources, one ResolvedArgOp per tuple. This exercises one arg of
# each of the four source kinds and asserts the op's fields match the tuple's
# payload exactly, field for field.
# ---------------------------------------------------------------------------

def _assert_resolved_matches_source(arg_name, op, src):
    """Assert a ResolvedArgOp is the exact mirror of its physics_arg_sources tuple."""
    op.verify()
    assert op.arg_name.data == arg_name
    kind = src[0]
    if kind == "host":
        assert op.source_kind.data == ArgSourceKind.Host
        assert op.var_name.data == src[1]
        assert op.module_name.data == src[2]
        assert op.member_path is None
        assert op.std_name is None
    elif kind == "ddt_member":
        assert op.source_kind.data == ArgSourceKind.DdtMember
        assert op.var_name.data == src[1]
        assert op.module_name.data == src[2]
        assert op.member_path.data == src[3]
        assert op.std_name is None
    elif kind == "cap_var":
        assert op.source_kind.data == ArgSourceKind.CapVar
        assert op.std_name.data == src[1]
        assert op.var_name is None
        assert op.module_name is None
        assert op.member_path is None
    else:
        assert kind == "block"
        assert op.source_kind.data == ArgSourceKind.Block
        assert op.var_name is None
        assert op.module_name is None
        assert op.member_path is None
        assert op.std_name is None


class TestResolvedArgOpFromSourceRejectsUnknownKind:
    """An unrecognized physics_arg_sources kind must raise, not silently
    become a Block op -- that would break the "pure mirror" guarantee and
    could mask a real classification bug."""

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError, match="Unrecognized physics_arg_sources kind"):
            _resolved_arg_op_from_source("x", ("bogus_kind",))

    def test_empty_tuple_raises_value_error_not_index_error(self):
        """An empty tuple must fail the same clear way as any other
        unrecognized kind, not with an uninformative IndexError."""
        with pytest.raises(ValueError, match="Unrecognized physics_arg_sources kind"):
            _resolved_arg_op_from_source("x", ())

    def test_block_kind_still_produces_block_op(self):
        """The one-tuple "block" tag itself is still handled explicitly."""
        op = _resolved_arg_op_from_source("x", ("block",))
        assert op.source_kind.data == ArgSourceKind.Block

    def test_block_kind_with_extra_payload_raises(self):
        """A malformed ("block", ...) tuple with extra fields must raise, not
        silently drop the extra payload -- host/ddt_member/cap_var all fail on
        unpack for the same kind of malformed tuple, so block should too."""
        with pytest.raises(ValueError):
            _resolved_arg_op_from_source("x", ("block", "unexpected_extra_field"))


class TestBuildResolvedArgOpsRejectsLengthMismatch:
    """callee_input_names and physics_arg_sources must be the same length --
    a silent zip()-style truncation/misalignment would break the "mirror"
    guarantee if the two ever diverged (e.g. a future refactor)."""

    def test_matching_lengths_succeed(self):
        ops = _build_resolved_arg_ops(["a", "b"], [("block",), ("block",)])
        assert [op.arg_name.data for op in ops] == ["a", "b"]

    def test_more_names_than_sources_raises(self):
        with pytest.raises(ValueError, match="diverged in length"):
            _build_resolved_arg_ops(["a", "b"], [("block",)])

    def test_more_sources_than_names_raises(self):
        with pytest.raises(ValueError, match="diverged in length"):
            _build_resolved_arg_ops(["a"], [("block",), ("block",)])


class TestBuildPerSuiteRunInfoResolvedArgOps:
    """resolved_arg_ops mirrors physics_arg_sources, one arg of each kind."""

    def _meta_data(self):
        # phys_scheme's _run table declares all four callee args directly, so
        # std_name_of picks them all up from the scheme table itself.
        scheme_props = _make_table_props(
            "phys_scheme", "scheme",
            _make_arg_table("phys_scheme_run", [
                # Host var: matched via model_var_name/model_module_name,
                # model_var_is_ddt unset -> plain host variable.
                _make_arg(
                    "temp", standard_name="air_temperature",
                    model_var_name="t_host", model_module_name="test_host_mod",
                ),
                # DDT member: model_module_name holds the DDT *type* name
                # (rad_t), resolved one level deep via ddt_parent_map below.
                _make_arg(
                    "rad_temp", standard_name="shortwave_heating_rate",
                    model_var_name="temp", model_module_name="rad_t",
                    model_var_is_ddt=True,
                ),
                # Cap var: no model_var_name match, but its standard_name is
                # in cap_var_map.
                _make_arg("vmr", standard_name="array_of_volume_mixing_ratios"),
                # Block: no model_var_name match, no standard_name at all, so
                # falls all the way through to the caller-block-arg default.
                _make_arg("unmatched_arg"),
            ], "scheme"),
        )
        scheme_props.arg_tables["phys_scheme_run"] = scheme_props.arg_tables.pop(
            "phys_scheme"
        )

        # test_host_mod must be a real MODULE-type entry so the DDT-member
        # branch's "is the instance a HOST-type table" check finds MODULE,
        # not HOST, and takes the ddt_member path instead of falling back
        # to block.
        mod_props = _make_table_props(
            "test_host_mod", "module",
            _make_arg_table("test_host_mod", [], "module"),
        )

        return {"phys_scheme": scheme_props, "test_host_mod": mod_props}

    def _maps(self):
        return _RunMetadataMaps(
            host_var_map={},
            host_block_std_names=set(),
            constituent_std_names=set(),
            ddt_type_names=set(),
            ddt_instance_map={"phys_state_t": ("phys_state", "test_host_mod")},
            ddt_parent_map={"rad_t": [("rad", "phys_state_t")]},
        )

    def test_resolved_arg_ops_mirror_physics_arg_sources(self):
        callee_input_names = ["temp", "rad_temp", "vmr", "unmatched_arg"]
        public_fns = {
            "test_suite_callee": (
                "test_suite_cap_mod",
                [],
                [None] * len(callee_input_names),
                callee_input_names,
            ),
        }
        suite_run_entries = [
            ("test_suite", "run", "test_suite_callee", ["phys_scheme"]),
        ]
        cap_var_map = {"array_of_volume_mixing_ratios": "vmr_ddt"}

        per_suite, _host_global_ops = _build_per_suite_run_info(
            suite_run_entries,
            public_fns,
            self._meta_data(),
            self._maps(),
            cap_var_map,
            seen_host_globals=set(),
        )

        assert len(per_suite) == 1
        info = per_suite[0]
        assert info["physics_arg_sources"] == [
            ("host", "t_host", "test_host_mod"),
            ("ddt_member", "phys_state", "test_host_mod", "rad%temp"),
            ("cap_var", "array_of_volume_mixing_ratios"),
            ("block",),
        ]
        assert len(info["resolved_arg_ops"]) == len(info["physics_arg_sources"])
        for arg_name, op, src in zip(
            callee_input_names, info["resolved_arg_ops"], info["physics_arg_sources"]
        ):
            _assert_resolved_matches_source(arg_name, op, src)
