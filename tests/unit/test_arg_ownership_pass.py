"""Validation tests for ArgOwnershipPass (Phase 7).

Phase 7, Stage 2 introduced ArgOwnershipPass as a dual-build alongside the
existing independently-computed heuristics (suite_cap.py's SuiteOwned gate,
ccpp_cap.py's HostMatched/CapScratch/Block split), verifying the new IR's
per-arg decisions agreed with those old mechanisms on every real example.
Stage 3 switched both consumers over to reading this classification instead,
and Stage 4 deleted the old heuristics entirely -- there is nothing left to
cross-check against, so that comparison test is gone. What remains is the
one check that's still meaningful on its own: no scheme arg should ever be
left unclassified.

Real examples are used deliberately here rather than small hand-built
fixtures: the point is confirming the pass classifies every scheme arg on
production metadata, including cases (host metadata, constituents, DDT
plumbing) synthetic fixtures could too easily get "conveniently" simple.
"""

from pathlib import Path

import pytest
from xdsl.context import Context
from xdsl.dialects.builtin import ModuleOp
from xdsl.universe import Universe
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp import CCPP, TableTypeKind
from xdsl_ccpp.dialects.ccpp_utils import CCPPUtils
from xdsl_ccpp.frontend.ccpp_xml import XMLSuite, ccppXML, parse_meta_file
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.host_var_match_pass import HostVariableMatchPass
from xdsl_ccpp.transforms.suite_meta import MetaCAP
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _make_context() -> Context:
    ctx = Context()
    for name, factory in Universe.get_multiverse().all_dialects.items():
        ctx.register_dialect(name, factory)
    ctx.load_dialect(CCPP)
    ctx.load_dialect(CCPPUtils)
    return ctx


def _build_real_example_module(suite_xml_path, scheme_meta_paths, host_meta_paths) -> ModuleOp:
    """Parse real example files directly off disk -- no temp-file indirection,
    since these are already real files, not string fixtures."""
    frontend = ccppXML()
    ir_ops = [frontend.build_suite_ir(XMLSuite(str(suite_xml_path)))]
    for p in scheme_meta_paths:
        for meta in parse_meta_file(str(p), True):
            ir_ops.append(frontend.build_meta_ir(meta))
    for p in host_meta_paths:
        for meta in parse_meta_file(str(p), False):
            ir_ops.append(frontend.build_meta_ir(meta))
    return ModuleOp(ir_ops)


# name -> (suite_xml, [scheme metas], [host metas])
_REAL_EXAMPLES = {
    "kessler": (
        _EXAMPLES / "kessler/scheme/kessler_suite.xml",
        [_EXAMPLES / "kessler/scheme/kessler.meta", _EXAMPLES / "kessler/scheme/kessler_update.meta"],
        [_EXAMPLES / "kessler/host_ftn/kessler_host_mod.meta"],
    ),
    "advection": (
        _EXAMPLES / "advection/cld_suite.xml",
        [
            _EXAMPLES / "advection/const_indices.meta",
            _EXAMPLES / "advection/cld_liq.meta",
            _EXAMPLES / "advection/cld_ice.meta",
            _EXAMPLES / "advection/apply_constituent_tendencies.meta",
        ],
        [
            _EXAMPLES / "advection/test_host_data.meta",
            _EXAMPLES / "advection/test_host.meta",
            _EXAMPLES / "advection/test_host_mod.meta",
        ],
    ),
    "helloworld": (
        _EXAMPLES / "helloworld/hello_world_suite.xml",
        [_EXAMPLES / "helloworld/hello_scheme.meta", _EXAMPLES / "helloworld/temp_adjust.meta"],
        [_EXAMPLES / "helloworld/hello_world_host.meta", _EXAMPLES / "helloworld/hello_world_mod.meta"],
    ),
}


def _actual_ownership_buckets(ctx, module) -> dict:
    """Run ArgOwnershipPass and return ownership_kind (or None) for every
    scheme arg, keyed by (scheme_name, table_name, arg_name)."""
    ccpp_mod = find_ccpp_module(module.body.block.ops)
    ArgOwnershipPass().apply(ctx, module)

    actual: dict = {}
    for table_prop_op in ccpp_mod.body.ops:
        if not isa(table_prop_op, ccpp.TablePropertiesOp):
            continue
        if table_prop_op.table_type.data != TableTypeKind.Scheme:
            continue
        scheme_name = table_prop_op.table_name.data

        for arg_table_op in table_prop_op.body.ops:
            if not isa(arg_table_op, ccpp.ArgumentTableOp):
                continue
            table_name = arg_table_op.table_name.data

            for arg_op in arg_table_op.body.ops:
                if not isa(arg_op, ccpp.ArgumentOp):
                    continue
                key = (scheme_name, table_name, arg_op.arg_name.data)
                actual[key] = arg_op.ownership_kind.data if arg_op.ownership_kind is not None else None

    return actual


@pytest.mark.parametrize("example_name", sorted(_REAL_EXAMPLES))
def test_every_scheme_arg_gets_classified(example_name):
    """No scheme arg should be left with ownership_kind unset."""
    suite_xml, scheme_metas, host_metas = _REAL_EXAMPLES[example_name]
    ctx = _make_context()
    module = _build_real_example_module(suite_xml, scheme_metas, host_metas)
    MetaCAP().apply(ctx, module)
    HostVariableMatchPass().apply(ctx, module)

    actual = _actual_ownership_buckets(ctx, module)
    assert actual, f"{example_name}: no scheme args found -- fixture paths are wrong"
    unset = [key for key, kind in actual.items() if kind is None]
    assert not unset, f"{example_name}: scheme args left unclassified: {unset}"
