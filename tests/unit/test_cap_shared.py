"""Unit tests for xdsl_ccpp.transforms.util.cap_shared.

_build_no_suite_matched_false_ops was added later, consolidating three
independent copies of the same "no suite matched" error sequence
(run_dispatch.py x2, lifecycle_cap.py x1) into one shared function.

_iter_schemes was added later still, consolidating ccpp_cap.py's and
suite_cap.py's independent copies of the same subcycle-flattening logic
(suite_variable_model.py has a third, deliberately separate copy -- see its
own comment for why it isn't unified here).

_collect_ddt_use_stubs and _rank_of were added later still, consolidating
ccpp_cap.py/suite_cap.py's identical DDT-USE-stub logic and
ccpp_cap.py/run_dispatch.py's identical type-rank expression respectively.

_assert_call_arg_count_matches_signature consolidates lifecycle_cap.py's and
run_dispatch.py's identical "Signature mismatch" check-and-raise, whose
wording had already started to diverge between the two copies.

split_scheme_table_name's _PHASE_SUFFIXES previously had no bare '_final'
entry (only '_finalize'/'_timestep_final'/'_timestep_finalize'), so a scheme
following the atmospheric_physics/kessler_update bare-form convention (e.g.
examples/advection's cld_ice_final) was silently never recognized as a
finalize table by any of its three consumers (lifecycle_cap.py's dispatch,
suite_cap.py's arg-table lookup, and the GPU passes' phase classification) --
not an error, just a table that never matched and so was never called.
"""

import pytest
from xdsl.dialects import memref, scf

from xdsl_ccpp.dialects.ccpp_utils import WriteErrMsgOp
from xdsl_ccpp.transforms.util.cap_shared import (
    LIFECYCLE_POSTFIX_ALIASES,
    _assert_call_arg_count_matches_signature,
    _build_no_suite_matched_false_ops,
    _collect_ddt_use_stubs,
    _iter_schemes,
    _rank_of,
    split_scheme_table_name,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    CCPPArgument,
    CCPPArgumentTable,
    XMLGroup,
    XMLScheme,
    XMLSubcycle,
)
from xdsl_ccpp.transforms.util.typing import TypeConversions


def _make_arg(name, **attrs):
    arg = CCPPArgument(name)
    for k, v in attrs.items():
        arg.setAttr(k, v)
    return arg


def _make_arg_table(args, name="tbl", table_type="scheme"):
    tbl = CCPPArgumentTable()
    tbl.setAttr("name", name)
    tbl.setAttr("type", table_type)
    for arg in args:
        tbl.setFunctionArgument(arg)
    return tbl


class TestBuildNoSuiteMatchedFalseOps:
    """_build_no_suite_matched_false_ops: the shared "no suite matched"
    fallback error sequence -- previously duplicated three ways
    (run_dispatch.py x2, lifecycle_cap.py x1), which is exactly the failure
    shape that let a Phase 3a review fix land on two copies and miss the
    third. Now a single implementation, directly testable."""

    def _fixture_operands(self):
        errmsg_dest = memref.AllocaOp.get(
            TypeConversions.getBaseType("character"), shape=[512]
        ).memref
        trim_suite_name_res = memref.AllocaOp.get(
            TypeConversions.getBaseType("character"), shape=[64]
        ).memref
        errflg_dest = memref.AllocaOp.get(
            TypeConversions.getBaseType("integer"), shape=[]
        ).memref
        return errmsg_dest, trim_suite_name_res, errflg_dest

    def test_returns_four_ops_in_order(self):
        errmsg_dest, trim_suite_name_res, errflg_dest = self._fixture_operands()
        ops = _build_no_suite_matched_false_ops(
            errmsg_dest, trim_suite_name_res, errflg_dest
        )
        assert len(ops) == 4
        write_err, one_err, store_errflg_err, yield_op = ops
        assert isinstance(write_err, WriteErrMsgOp)
        assert isinstance(store_errflg_err, memref.StoreOp)
        assert isinstance(yield_op, scf.YieldOp)

    def test_error_message_text_has_leading_and_trailing_space(self):
        """Prefix ends and suffix starts with a space so the trimmed suite
        name reads correctly on both sides: "No suite named <name> found"."""
        errmsg_dest, trim_suite_name_res, errflg_dest = self._fixture_operands()
        write_err, _one_err, _store, _yield = _build_no_suite_matched_false_ops(
            errmsg_dest, trim_suite_name_res, errflg_dest
        )
        assert write_err.prefix.data == "No suite named "
        assert write_err.suffix.data == " found"

    def test_writes_to_the_given_errmsg_and_var_operands(self):
        errmsg_dest, trim_suite_name_res, errflg_dest = self._fixture_operands()
        write_err, _one_err, _store, _yield = _build_no_suite_matched_false_ops(
            errmsg_dest, trim_suite_name_res, errflg_dest
        )
        assert write_err.dest == errmsg_dest
        assert write_err.var == trim_suite_name_res

    def test_sets_errflg_to_one_on_the_given_dest(self):
        errmsg_dest, trim_suite_name_res, errflg_dest = self._fixture_operands()
        _write, one_err, store_errflg_err, _yield = _build_no_suite_matched_false_ops(
            errmsg_dest, trim_suite_name_res, errflg_dest
        )
        assert one_err.value.value.data == 1
        assert store_errflg_err.memref == errflg_dest


class TestIterSchemes:
    """_iter_schemes: yield a group's XMLScheme leaves, flattening one level
    of XMLSubcycle nesting."""

    def test_plain_schemes_yielded_directly(self):
        group = XMLGroup("physics")
        group.addChild(XMLScheme("scheme_a"))
        group.addChild(XMLScheme("scheme_b"))
        names = [s.attributes["name"] for s in _iter_schemes(group)]
        assert names == ["scheme_a", "scheme_b"]

    def test_subcycle_schemes_flattened(self):
        group = XMLGroup("physics")
        subcycle = XMLSubcycle(loop_count=2)
        subcycle.addChild(XMLScheme("scheme_a"))
        subcycle.addChild(XMLScheme("scheme_b"))
        group.addChild(subcycle)
        names = [s.attributes["name"] for s in _iter_schemes(group)]
        assert names == ["scheme_a", "scheme_b"]

    def test_mixed_plain_and_subcycle_schemes_preserve_order(self):
        group = XMLGroup("physics")
        subcycle = XMLSubcycle(loop_count=3)
        subcycle.addChild(XMLScheme("scheme_b"))
        subcycle.addChild(XMLScheme("scheme_c"))
        group.addChild(XMLScheme("scheme_a"))
        group.addChild(subcycle)
        group.addChild(XMLScheme("scheme_d"))
        names = [s.attributes["name"] for s in _iter_schemes(group)]
        assert names == ["scheme_a", "scheme_b", "scheme_c", "scheme_d"]

    def test_empty_group_yields_nothing(self):
        group = XMLGroup("physics")
        assert list(_iter_schemes(group)) == []


class TestCollectDdtUseStubs:
    """_collect_ddt_use_stubs: llvm.GlobalOp USE-association stubs for DDT
    types referenced by scheme args -- previously duplicated identically in
    ccpp_cap.py (_generate_ccpp_cap_module) and suite_cap.py
    (_build_ddt_use_stubs)."""

    def test_ddt_typed_arg_gets_a_stub(self):
        tbl = _make_arg_table([_make_arg("x", type="vmr_type")])
        stubs = _collect_ddt_use_stubs([tbl], {"vmr_type": "vmr_mod"})
        assert len(stubs) == 1
        assert stubs[0].sym_name.data == "vmr_type"
        assert stubs[0].attributes["module"].data == "vmr_mod"

    def test_primitive_typed_arg_gets_no_stub(self):
        tbl = _make_arg_table([_make_arg("x", type="real")])
        stubs = _collect_ddt_use_stubs([tbl], {"real": "should_never_be_used"})
        assert stubs == []

    def test_ddt_type_with_no_source_module_gets_no_stub(self):
        tbl = _make_arg_table([_make_arg("x", type="unregistered_type")])
        stubs = _collect_ddt_use_stubs([tbl], {})
        assert stubs == []

    def test_arg_without_type_attr_is_skipped(self):
        tbl = _make_arg_table([_make_arg("x")])
        stubs = _collect_ddt_use_stubs([tbl], {"vmr_type": "vmr_mod"})
        assert stubs == []

    def test_same_ddt_type_deduped_within_one_arg_table(self):
        tbl = _make_arg_table([
            _make_arg("x", type="vmr_type"),
            _make_arg("y", type="vmr_type"),
        ])
        stubs = _collect_ddt_use_stubs([tbl], {"vmr_type": "vmr_mod"})
        assert len(stubs) == 1

    def test_same_ddt_type_deduped_across_multiple_arg_tables(self):
        tbl1 = _make_arg_table([_make_arg("x", type="vmr_type")], name="tbl1")
        tbl2 = _make_arg_table([_make_arg("y", type="vmr_type")], name="tbl2")
        stubs = _collect_ddt_use_stubs([tbl1, tbl2], {"vmr_type": "vmr_mod"})
        assert len(stubs) == 1

    def test_external_seen_set_is_respected(self):
        """A caller-provided seen set lets stubs already emitted elsewhere be
        skipped here too."""
        seen = {"vmr_type"}
        tbl = _make_arg_table([_make_arg("x", type="vmr_type")])
        stubs = _collect_ddt_use_stubs([tbl], {"vmr_type": "vmr_mod"}, seen=seen)
        assert stubs == []


class TestRankOf:
    """_rank_of: dimension count of an xDSL type, 0 for anything without a
    shape -- previously duplicated identically in ccpp_cap.py
    (_build_cap_var_map) and run_dispatch.py (_build_run_dispatch_chain)."""

    def test_memref_type_returns_rank(self):
        t = memref.MemRefType(TypeConversions.getBaseType("real"), [10, 20])
        assert _rank_of(t) == 2

    def test_rank_one_memref_type(self):
        t = memref.MemRefType(TypeConversions.getBaseType("real"), [10])
        assert _rank_of(t) == 1

    def test_scalar_type_without_shape_returns_zero(self):
        t = TypeConversions.getBaseType("real")
        assert _rank_of(t) == 0

    def test_none_returns_zero(self):
        assert _rank_of(None) == 0


class TestAssertCallArgCountMatchesSignature:
    """_assert_call_arg_count_matches_signature: the shared "Signature
    mismatch" check-and-raise -- previously duplicated in lifecycle_cap.py
    and run_dispatch.py, with wording that had already started to diverge."""

    def test_matching_counts_does_not_raise(self):
        _assert_call_arg_count_matches_signature(
            "test_suite_run", ["a", "b"], ["arg1", "arg2"], ["type1", "type2"]
        )

    def test_fewer_args_than_expected_raises(self):
        with pytest.raises(ValueError, match="Signature mismatch for 'test_suite_run'"):
            _assert_call_arg_count_matches_signature(
                "test_suite_run", ["a"], ["arg1", "arg2"], ["type1", "type2"]
            )

    def test_more_args_than_expected_raises(self):
        with pytest.raises(ValueError, match="Signature mismatch for 'test_suite_run'"):
            _assert_call_arg_count_matches_signature(
                "test_suite_run", ["a", "b", "c"], ["arg1", "arg2"], ["type1", "type2"]
            )

    def test_error_message_includes_counts_and_names(self):
        with pytest.raises(ValueError) as excinfo:
            _assert_call_arg_count_matches_signature(
                "test_suite_run", ["a"], ["arg1", "arg2"], ["type1", "type2"]
            )
        msg = str(excinfo.value)
        assert "generated 1 input arg(s) but callee expects 2" in msg
        assert "Callee inputs:" in msg
        assert "Generated args:" in msg


class TestSplitSchemeTableNameFinalAlias:
    """split_scheme_table_name: a scheme's finalize table can be named either
    the canonical '<scheme>_finalize' or the atmospheric_physics/
    kessler_update bare-form '<scheme>_final' -- both must resolve to the
    same ('<scheme>', 'finalize') phase, matching the '_init'/'_timestep_init'
    /'_timestep_final' short-form aliases this function already accepted."""

    def test_bare_final_suffix_resolves_to_finalize_phase(self):
        assert split_scheme_table_name("cld_ice_final") == ("cld_ice", "finalize")

    def test_canonical_finalize_suffix_still_resolves(self):
        assert split_scheme_table_name("cld_ice_finalize") == ("cld_ice", "finalize")

    def test_timestep_final_not_shadowed_by_bare_final(self):
        assert split_scheme_table_name("kessler_update_timestep_final") == (
            "kessler_update", "timestep_final",
        )

    def test_timestep_finalize_not_shadowed_by_bare_final(self):
        assert split_scheme_table_name("kessler_update_timestep_finalize") == (
            "kessler_update", "timestep_final",
        )

    def test_lifecycle_postfix_aliases_maps_finalize_to_final(self):
        assert LIFECYCLE_POSTFIX_ALIASES["_finalize"] == "_final"
