"""Unit tests for cross-variable update self/device coalescing in
GPUDataPass -- cap_shared.emit_coalesced_updates, shared with
suite_cap.py's SuiteOwned handling (see test_suite_owned_residency.py's own
test_two_vars_sharing_a_boundary_get_coalesced_into_one_update).

Before this feature, GPUDataPass emitted one update self/device pair per
diverged variable even when two different variables' own update runs
shared the exact same triggering-call boundary -- and a HostMatched var's
divergence (_process_diverged_host_vars) and a CapScratch var's divergence
(_process_diverged_capscratch_vars) were routed through two entirely
separate calls into the coalescing core, so they could never be grouped
together even when they diverged at the identical point in the same suite.
This suite proves both kinds are merged into a single call when their
boundaries coincide.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.gpu_ccpp_cap_pass import GPUCcppCapPass
from xdsl_ccpp.transforms.gpu_data_pass import GPUDataPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

import pytest

pytestmark = pytest.mark.usefixtures("legacy_mode")


def _fortran_output(run_host_match, ccpp_context, scheme_metas, host_metas, suite_xml) -> str:
    module = run_host_match(
        scheme_metas=scheme_metas,
        host_metas=host_metas,
        suite_xml=suite_xml,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    GPUDataPass(directive="acc").apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    GPUCcppCapPass(directive="acc").apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fn_body(fortran: str, fn_name: str) -> str:
    return fortran.split(f"subroutine {fn_name}")[1].split(f"end subroutine {fn_name}")[0]


# scheme_a: "wants present" for BOTH a HostMatched var (qv_a, device host)
# and a CapScratch var (const_tend, the framework-mapped ccpp_constituent_
# tendencies array) -- also registers the constituent, as
# test_capscratch_divergence.py's own _DIRECT_PRODUCER_SCHEME does.
_MERGE_SCHEME_A = f"""\
[ccpp-table-properties]
  name = test_merge_scheme_a
  type = scheme
[ccpp-arg-table]
  name = test_merge_scheme_a_register
  type = scheme
[ dyn_const ]
  standard_name = dynamic_constituents_for_test_merge
  dimensions = (:)
  type = ccpp_constituent_properties_t
  intent = out
  allocatable = true
[ errmsg ]
  standard_name = ccpp_error_message
  units = none
  dimensions = ()
  type = character
  kind = len=512
  intent = out
[ errflg ]
  standard_name = ccpp_error_code
  units = 1
  dimensions = ()
  type = integer
  intent = out
[ccpp-arg-table]
  name = test_merge_scheme_a_run
  type = scheme
[ qv_a ]
  standard_name = test_merge_conflict_var
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = inout
[ const_tend ]
  standard_name = ccpp_constituent_tendencies
  units = none
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension, number_of_ccpp_constituents)
  intent = inout
  memory_space = device
{CCPP_MANDATORY_ARGS}
"""

# scheme_b: "wants update" for BOTH the same host-matched var and the same
# CapScratch var -- both diverge from scheme_a at the exact same call, so
# both should land in the SAME update self/device pair.
_MERGE_SCHEME_B = f"""\
[ccpp-table-properties]
  name = test_merge_scheme_b
  type = scheme
[ccpp-arg-table]
  name = test_merge_scheme_b_run
  type = scheme
[ qv_b ]
  standard_name = test_merge_conflict_var
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
[ const_tend ]
  standard_name = ccpp_constituent_tendencies
  units = none
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension, number_of_ccpp_constituents)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_MERGE_HOST_META = """\
[ccpp-table-properties]
  name = test_merge_host
  type = module
[ccpp-arg-table]
  name = test_merge_host
  type = module
[ conflict_var ]
  standard_name = test_merge_conflict_var
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
"""

_MERGE_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_merge_suite" version="1.0">
  <group name="physics">
    <scheme>test_merge_scheme_a</scheme>
    <scheme>test_merge_scheme_b</scheme>
  </group>
</suite>
"""


class TestHostMatchedAndCapScratchCoalescing:
    def test_diverged_host_var_and_capscratch_var_share_one_update_pair(
        self, run_host_match, ccpp_context
    ):
        """qv (HostMatched) and const_tend (CapScratch) both diverge at
        scheme_b's own call -- exactly one update self(...) and one update
        device(...) pair should be emitted for the whole function, each
        listing both variables, rather than two separate single-var
        pairs."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_MERGE_SCHEME_A, _MERGE_SCHEME_B], [_MERGE_HOST_META], _MERGE_SUITE_XML,
        )
        suite_fn = _fn_body(fortran, "test_merge_suite_physics")

        assert suite_fn.count("update self(") == 1
        assert suite_fn.count("update device(") == 1

        self_line = next(
            line for line in suite_fn.splitlines() if "update self(" in line
        )
        device_line = next(
            line for line in suite_fn.splitlines() if "update device(" in line
        )
        # suite_cap.py unifies same-standard_name args across schemes into
        # one shared block-arg parameter, named after whichever scheme's
        # local name was encountered first (scheme_a's "qv_a") -- not the
        # scheme whose call actually triggers the sync (scheme_b's "qv_b").
        assert "qv_a" in self_line and "const_tend" in self_line
        assert "qv_a" in device_line and "const_tend" in device_line
