"""A scheme arg declared `advected = true` whose standard name the cap
registers as a constituent is passed in by the host cap, as in capgen: a
pointer view `lc_<name> => lc_constituent_array(:, :, idx)`, associated in
<host>_ccpp_initialize_constituents and passed in every phase. The suite cap
owns no storage for it.

Before, such args were SuiteOwned arrays the suite cap aliased or copied
into the constituent array, but only when some scheme took the whole array
(ccpp_constituents) and only in _run; CAM-SIMA's cloud_water suite has
neither, so its schemes read arrays nothing ever filled.
"""

import os
import re

import pytest

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.dialects.ccpp import ArgOwnershipKind
from xdsl_ccpp.tools.ccpp_dsl import ccppMain
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.constituent_cap import host_bound_constituent_std_names
from xdsl_ccpp.transforms.util.ccpp_descriptors import BuildMetaDataDescriptions
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module


def _generate(tmp_path, example, suite, schemes, hosts, **extra):
    """Generate an example's caps; return (suite cap text, host cap text)."""
    ex = f"examples/{example}"
    tool = ccppMain()
    options_db = tool.default_options_db()
    options_db.update({
        "suites": [f"{ex}/{suite}"],
        "scheme_files": [f"{ex}/{n}.meta" for n in schemes],
        "host_files": [f"{ex}/{n}.meta" for n in hosts],
        "out": str(tmp_path / "out"),
        "tempdir": str(tmp_path / "tmp"),
        "verbose": 0,
        **extra,
    })
    result = tool.run(options_db)
    caps = {os.path.basename(p): open(os.path.join(options_db["out"], p)).read()
            for p in result.written if p.endswith(".F90")}
    host = next(t for n, t in caps.items() if n.endswith("_ccpp_cap.F90"))
    suite_cap = next(t for n, t in caps.items()
                     if n.endswith("_cap.F90") and not n.endswith("_ccpp_cap.F90"))
    return suite_cap, host


def _unwrapped(text):
    return re.sub(r"&\s*\n\s*", "", text)


def _call(text, callee):
    """The argument text of the (unwrapped) call to callee."""
    return re.search(rf"call {callee}\((.*)\)\s*$", text, re.M).group(1)


def test_run_phase_arg_without_constituent_array_scheme(tmp_path):
    """examples/constituents_dim: qbase is advected and no scheme takes
    ccpp_constituents (the cloud_water case)."""
    suite, host = _generate(
        tmp_path, "constituents_dim", "constituents_dim_suite.xml",
        ["register_consts", "const_dim_producer", "const_dim_consumer"],
        ["host_data", "test_host"], host_name="test_host",
    )
    suite, host = _unwrapped(suite), _unwrapped(host)
    assert not re.search(r"::\s*qbase\b", suite.split("CONTAINS")[0])
    assert "lc_const_indices" not in suite
    assert re.search(r"intent\(inout\) :: qbase\(:, :\)", suite)
    assert re.search(r"pointer :: lc_qbase\(:, :\)", host)
    assert re.search(r"lc_qbase => lc_constituent_array\(:, :, lc_tend_idx\)", host)
    # qbase is dimensioned horizontal_dimension, so the view is passed whole.
    assert re.search(r"\blc_qbase\b", _call(host, "constituents_dim_suite_const_group"))
    # The view is the host cap's own: ccpp_physics_run's signature is unchanged.
    sig = re.search(r"subroutine ccpp_physics_run\(([^)]*)\)", host).group(1)
    assert "qbase" not in sig


def test_init_phase_arg_and_name_collision(tmp_path):
    """examples/advection: cld_liq_array (init only) and cld_ice_array
    (init and run) are views in every phase; cld_shadow's own, unrelated
    cld_ice_array stays a suite variable, renamed so the dummy does not
    shadow it."""
    suite, host = _generate(
        tmp_path, "advection", "cld_suite.xml",
        ["const_indices", "cld_liq", "cld_ice", "apply_constituent_tendencies", "cld_shadow"],
        ["test_host_data", "test_host_mod", "test_host"], host_name="test_host",
    )
    suite, host = _unwrapped(suite), _unwrapped(host)
    module_scope = suite.split("CONTAINS")[0]
    assert not re.search(r"::\s*cld_liq_array\b", module_scope)
    assert not re.search(r"::\s*cld_ice_array\b", module_scope)
    assert re.search(r"allocatable :: cld_shadow_cld_ice_array\(:, :\)", module_scope)
    assert "cld_shadow_run(" in suite
    assert re.search(r"cld_shadow_run\([^)]*cld_ice_array=cld_shadow_cld_ice_array", suite)
    init_call = _call(host, "cld_suite_init_physics")
    assert "lc_cld_liq_array(col_start:col_end" in init_call
    assert "lc_cld_ice_array(col_start:col_end" in init_call
    run_call = _call(host, "cld_suite_physics")
    assert "lc_cld_ice_array(col_start:col_end" in run_call


def test_device_views_copied_per_call(tmp_path):
    """examples/advection with --directive acc: each device call that takes
    a constituent view gets its own copy() region; lc_constituent_array is
    never made resident (the host updates the constituents between calls)."""
    suite, host = _generate(
        tmp_path, "advection", "cld_suite.xml",
        ["const_indices", "cld_liq", "cld_ice", "apply_constituent_tendencies", "cld_shadow"],
        ["test_host_data", "test_host_mod", "test_host"], host_name="test_host",
        directive="acc",
    )
    for callee, view in [("cld_liq_init", "cld_liq_array"),
                         ("cld_ice_init", "cld_ice_array"),
                         ("cld_ice_run", "cld_ice_array")]:
        assert re.search(
            rf"!\$acc data copy\({view}\)\s*\n(?:#endif\s*\n)?(?:#ifdef USE_GPU\s*\n)?"
            rf"\s*if \(errflg \.eq\. 0\) then\s*\n\s*call {callee}\(", suite
        ), callee
    assert not re.search(r"present\(cld_(liq|ice)_array\)", suite)
    assert not re.search(r"enter data [^\n]*lc_constituent_array", host)


def test_multi_instance_views(tmp_path):
    suite, host = _generate(
        tmp_path, "instances_advection", "cld_suite.xml",
        ["cld_liq", "apply_constituent_tendencies"], ["data", "test_host"],
    )
    host = _unwrapped(host)
    assert "lc_const_indices" not in suite
    assert re.search(r"lc_instances\(\w+\)%lc_cld_liq_array\(lb:ub", _call(host, "cld_suite_physics"))


def _scheme(name, std_name, phase="run", extra=""):
    return f"""\
[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_{phase}
  type = scheme
[ ncol ]
  standard_name = horizontal_loop_extent
  units = count
  type = integer
  dimensions = ()
  intent = in
[ q ]
  standard_name = {std_name}
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
  advected = true
{CCPP_MANDATORY_ARGS}{extra}"""


_HOST = """\
[ccpp-table-properties]
  name = binding_host
  type = module
[ccpp-arg-table]
  name = binding_host
  type = module
[ pver ]
  standard_name = vertical_layer_dimension
  units = count
  type = integer
  dimensions = ()
"""


def _ownership(module, scheme, arg="q"):
    for op in find_ccpp_module(module.body.block.ops).walk():
        if getattr(op, "name", "") == "ccpp.arg" and op.arg_name.data == arg:
            table = op.parent_op()
            if table.table_name.data.startswith(scheme):
                return op.ownership_kind.data
    raise AssertionError(f"{scheme}.{arg} not found")


def test_dry_air_form_stays_suite_owned(run_host_match, ccpp_context, legacy_mode):
    """A *_wrt_dry_air form whose moist form is also advected is not a
    registered constituent (wet_to_dry_* schemes produce it), so it stays a
    suite variable; the moist form is host-bound."""
    moist = "water_vapor_mixing_ratio_wrt_moist_air_and_condensed_water"
    dry = "water_vapor_mixing_ratio_wrt_dry_air"
    module = run_host_match(
        scheme_metas=[_scheme("moist_scheme", moist), _scheme("dry_scheme", dry)],
        host_metas=[_HOST],
        suite_xml=minimal_suite_xml("moist_scheme").replace(
            "<scheme>moist_scheme</scheme>",
            "<scheme>moist_scheme</scheme>\n    <scheme>dry_scheme</scheme>"),
    )
    bmdd = BuildMetaDataDescriptions()
    bmdd.traverse(find_ccpp_module(module.body.block.ops))
    assert host_bound_constituent_std_names(bmdd.meta_data) == {moist}
    ArgOwnershipPass().apply(ccpp_context, module)
    assert _ownership(module, "moist_scheme") == ArgOwnershipKind.CapScratch
    assert _ownership(module, "dry_scheme") == ArgOwnershipKind.SuiteOwned


def test_register_phase_constituent_arg_is_an_error(run_host_match, ccpp_context, legacy_mode):
    """Constituent data exists only after the constituents are initialized."""
    std = "test_tracer_mixing_ratio"
    meta = _scheme("reg_scheme", std) + f"""\
[ccpp-arg-table]
  name = reg_scheme_register
  type = scheme
[ q ]
  standard_name = {std}
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  intent = inout
  advected = true
{CCPP_MANDATORY_ARGS}"""
    module = run_host_match(
        scheme_metas=[meta], host_metas=[_HOST],
        suite_xml=minimal_suite_xml("reg_scheme"),
    )
    with pytest.raises(ValueError, match="_register phase"):
        ArgOwnershipPass().apply(ccpp_context, module)
