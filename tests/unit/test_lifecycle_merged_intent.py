"""A lifecycle-phase variable one scheme writes and a later one reads.

The suite cap combines the intents the schemes of one phase declare; any
two different ones make the variable intent(inout) in the suite subroutine,
returned in its leading inout section (suitecap/phase_functions.py). The
host-cap wrappers rebuilt that return list from each scheme's own intent
(_get_suite_lifecycle_ret_info / _get_suite_leading_inout_ret_info), saw
"out", and counted it among the trailing outputs: every copy-back shifted by
one (xdsl76g cam4: one_mom_clouds, intent(out) in prognostic_cloud_water_init
and intent(in) in cloud_water_paths_diagnostics_init, so the init wrapper
copied it into errmsg -- "Expected source and destination to have the same
shape")."""

import re
from io import StringIO

from xdsl.dialects.builtin import ModuleOp

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.suite_cap import SuiteCAP
from xdsl_ccpp.transforms.util.cap_shared import (
    _get_suite_leading_inout_ret_info,
    _get_suite_lifecycle_ret_info,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import BuildMetaDataDescriptions
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module

_FLAG = """\
[ flag ]
  standard_name = test_one_moment_flag
  units = flag
  type = logical
  dimensions = ()
  intent = {intent}
"""

_LEVEL = """\
[ top_lev ]
  standard_name = test_top_level_index
  units = index
  type = integer
  dimensions = ()
  intent = out
"""


def _scheme(name, init_args, run=False):
    meta = (
        f"[ccpp-table-properties]\n  name = {name}\n  type = scheme\n"
        f"[ccpp-arg-table]\n  name = {name}_init\n  type = scheme\n"
        f"{init_args}{CCPP_MANDATORY_ARGS}"
    )
    if run:
        meta += (f"[ccpp-arg-table]\n  name = {name}_run\n  type = scheme\n"
                 f"{CCPP_MANDATORY_ARGS}")
    return meta


_WRITER = _scheme("writer", _FLAG.format(intent="out") + _LEVEL, run=True)
_READER = _scheme("reader", _FLAG.format(intent="in"))

_HOST = """\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
[ flag_h ]
  standard_name = test_one_moment_flag
  units = flag
  type = logical
  dimensions = ()
[ top_lev_h ]
  standard_name = test_top_level_index
  units = index
  type = integer
  dimensions = ()
"""

_SUITE = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <scheme>writer</scheme>
    <scheme>reader</scheme>
  </group>
</suite>
"""


def _module(run_host_match, ccpp_context) -> ModuleOp:
    module = run_host_match(
        scheme_metas=[_WRITER, _READER], host_metas=[_HOST], suite_xml=_SUITE,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    return module


def test_return_lists_use_the_suite_level_intent(run_host_match, ccpp_context):
    module = _module(run_host_match, ccpp_context)
    bmdd = BuildMetaDataDescriptions()
    bmdd.traverse(find_ccpp_module(module.body.block.ops))
    names = ["writer", "reader"]
    outs = [std for _t, _n, std in _get_suite_lifecycle_ret_info(names, bmdd.meta_data, "_init")]
    inouts = [std for _n, std in _get_suite_leading_inout_ret_info(names, bmdd.meta_data, "_init")]
    assert "test_one_moment_flag" not in outs
    assert inouts == ["test_one_moment_flag"]
    assert "test_top_level_index" in outs


def test_init_wrapper_generates(run_host_match, ccpp_context):
    module = _module(run_host_match, ccpp_context)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    module.verify()
    out = StringIO()
    print_to_ftn(module, out)
    fortran = out.getvalue()
    suite_fn = fortran.split("subroutine test_suite_init_physics(")[1].split(
        "end subroutine test_suite_init_physics")[0]
    assert re.search(r"logical, intent\(inout\) :: flag\b", suite_fn)
    # The wrapper passes the host's flag in and gets it back in the inout
    # position, then the outputs (top_lev, errmsg, errflg) in theirs.
    assert "call test_suite_init_physics(flag_h, top_lev_h, errmsg, errflg)" in fortran
