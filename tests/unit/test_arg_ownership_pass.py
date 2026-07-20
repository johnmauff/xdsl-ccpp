"""Validation tests for ArgOwnershipPass (Phase 7, Stage 2).

Stage 2's mandate (see ccpp_cap_refactor_plan.md): compute the ownership
classification early and durably, *alongside* the existing independently-
computed heuristics (suite_cap.py's _is_framework_managed, ccpp_cap.py's
_build_cap_var_map), without switching any consumer -- then verify the new
IR's per-arg decisions actually match what those old mechanisms decide, for
every existing (real, not synthetic) example.

Real examples are used deliberately here rather than small hand-built
fixtures: the whole point of this stage is confirming the new pass agrees
with production heuristics on production metadata, including cases (host
metadata, constituents, DDT plumbing) synthetic fixtures could too easily
get "conveniently" simple.
"""

from pathlib import Path

import pytest
from xdsl.context import Context
from xdsl.dialects.builtin import ModuleOp
from xdsl.universe import Universe
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp import CCPP, ArgOwnershipKind, TableTypeKind
from xdsl_ccpp.dialects.ccpp_utils import CCPPUtils
from xdsl_ccpp.frontend.ccpp_xml import XMLSuite, ccppXML, parse_meta_file
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import (
    _build_cap_var_map,
    _collect_public_suite_functions,
)
from xdsl_ccpp.transforms.host_var_match_pass import HostVariableMatchPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP
from xdsl_ccpp.transforms.suite_meta import MetaCAP
from xdsl_ccpp.transforms.util.cap_shared import (
    _is_framework_managed,
    split_scheme_table_name,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    BuildSchemeDescription,
)
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


def _expected_and_actual_buckets(ctx, module):
    """Run the new pass plus the full pipeline needed to call the old
    heuristics for real, then return (expected, actual) dicts keyed by
    (scheme_name, table_name, arg_name)."""
    ccpp_mod = find_ccpp_module(module.body.block.ops)
    ArgOwnershipPass().apply(ctx, module)
    SuiteCAP().apply(ctx, module)  # needed to get real public_fns below

    bmdd = BuildMetaDataDescriptions()
    bmdd.traverse(ccpp_mod)
    meta_data = bmdd.meta_data

    bsd = BuildSchemeDescription()
    bsd.traverse(ccpp_mod)
    suite_descriptions = bsd.schemes

    public_fns = _collect_public_suite_functions(module.body.block.ops)
    cap_var_map, host_var_map_lc, _scratch = _build_cap_var_map(
        meta_data, suite_descriptions, public_fns
    )

    expected: dict = {}
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

                descriptor = meta_data[scheme_name].getArgTable(table_name).getFunctionArgument(
                    arg_op.arg_name.data
                )
                if _is_framework_managed(descriptor):
                    expected[key] = ArgOwnershipKind.SuiteOwned
                elif arg_op.model_var_name is not None:
                    expected[key] = ArgOwnershipKind.HostMatched
                else:
                    # _build_cap_var_map is scoped to the physics/"_run" group
                    # callee only -- it never even looks at register/init/
                    # finalize-only args (e.g. a constituent-registration arg
                    # declared only in a scheme's own "_register" table), so
                    # there's no old-heuristic ground truth to compare against
                    # for those. Only assert the CapScratch-vs-Block split for
                    # args _build_cap_var_map actually had a chance to see.
                    split = split_scheme_table_name(table_name)
                    in_run_scope = split is not None and split[1] == "run"
                    if not in_run_scope:
                        continue
                    if arg_op.standard_name is not None and arg_op.standard_name.data.lower() in cap_var_map:
                        expected[key] = ArgOwnershipKind.CapScratch
                    else:
                        expected[key] = ArgOwnershipKind.Block

    return expected, actual


@pytest.mark.parametrize("example_name", sorted(_REAL_EXAMPLES))
def test_ownership_matches_old_heuristics(example_name):
    """For every scheme arg in a real example, ArgOwnershipPass's decision
    must match what _is_framework_managed + _build_cap_var_map already
    decide today."""
    suite_xml, scheme_metas, host_metas = _REAL_EXAMPLES[example_name]
    ctx = _make_context()
    module = _build_real_example_module(suite_xml, scheme_metas, host_metas)
    MetaCAP().apply(ctx, module)
    HostVariableMatchPass().apply(ctx, module)

    expected, actual = _expected_and_actual_buckets(ctx, module)

    assert actual, f"{example_name}: no scheme args found -- fixture paths are wrong"
    mismatches = {
        key: (expected[key], actual[key])
        for key in expected
        if expected[key] != actual[key]
    }
    assert not mismatches, (
        f"{example_name}: ArgOwnershipPass disagrees with the old heuristics on "
        f"{len(mismatches)} arg(s) (scheme, table, arg) -> (expected, actual): {mismatches}"
    )


@pytest.mark.parametrize("example_name", sorted(_REAL_EXAMPLES))
def test_every_scheme_arg_gets_classified(example_name):
    """No scheme arg should be left with ownership_kind unset."""
    suite_xml, scheme_metas, host_metas = _REAL_EXAMPLES[example_name]
    ctx = _make_context()
    module = _build_real_example_module(suite_xml, scheme_metas, host_metas)
    MetaCAP().apply(ctx, module)
    HostVariableMatchPass().apply(ctx, module)

    _expected, actual = _expected_and_actual_buckets(ctx, module)
    unset = [key for key, kind in actual.items() if kind is None]
    assert not unset, f"{example_name}: scheme args left unclassified: {unset}"
