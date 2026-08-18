"""Regression coverage for the cross-phase interstitial-variable mechanism.

Real capgen-v1's own rule (generator/suite_resolver.py's module docstring,
"Section 8.4"): a scheme argument whose standard_name is never host-declared,
first used intent(out), is a suite-owned ("interstitial") variable -- the
framework synthesizes storage for it. examples/capgen's own upstream
temp_adjust.meta exercises exactly this cross-phase (produced in one scheme's
_run, consumed by a different scheme's _finalize -- separate generated Fortran
subroutines, called independently by the host) via its interstitial_var arg.

Scoped 2026-08-17 (ccpp_cap_refactor_plan.md's "Interstitial-variable
register-phase mechanism" entry): detection (is_interstitial), ownership
classification (SuiteOwned), module-level storage declaration, and guarded
lazy allocation were all found already implemented -- this test locks in the
one case actually verified end-to-end (isolated from examples/capgen's own
larger DDT/multi-suite complexity, which the frontend/completed_ir/end_to_end
capgen-xml.mlir filecheck goldens already cover for the real example).

Deliberately NOT covered here: the confirmed real ordering bug when an
interstitial's own dimension is itself a same-phase SuiteOwned producer (see
the "Chained-interstitial allocation-ordering bug" backlog entry) -- this
test's interstitial array is sized from genuine host state instead, exactly
the working case.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <scheme>scheme_producer</scheme>
    <scheme>scheme_consumer</scheme>
  </group>
</suite>
"""

_SCHEME_PRODUCER_META = f"""\
[ccpp-table-properties]
  name = scheme_producer
  type = scheme
[ccpp-arg-table]
  name = scheme_producer_run
  type = scheme
[ some_state ]
  standard_name = some_host_state_array
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  intent = inout
[ produced ]
  standard_name = my_interstitial_value
  units = 1
  type = integer
  dimensions = (horizontal_dimension)
  intent = out
{CCPP_MANDATORY_ARGS}
"""

_SCHEME_CONSUMER_META = f"""\
[ccpp-table-properties]
  name = scheme_consumer
  type = scheme
[ccpp-arg-table]
  name = scheme_consumer_finalize
  type = scheme
[ consumed ]
  standard_name = my_interstitial_value
  units = 1
  type = integer
  dimensions = (horizontal_dimension)
  intent = in
{CCPP_MANDATORY_ARGS}
"""

_HOST_META = """\
[ccpp-table-properties]
  name = test_host
  type = host
[ccpp-arg-table]
  name = test_host
  type = host
[ col_start ]
  standard_name = horizontal_loop_begin
  type = integer
  units = count
  dimensions = ()
  protected = True
  intent = in
[ col_end ]
  standard_name = horizontal_loop_end
  type = integer
  units = count
  dimensions = ()
  protected = True
  intent = in
[ some_state ]
  standard_name = some_host_state_array
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  intent = inout
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
"""


def _fortran_output(run_host_match, ccpp_context) -> str:
    module = run_host_match(
        scheme_metas=[_SCHEME_PRODUCER_META, _SCHEME_CONSUMER_META],
        host_metas=[_HOST_META],
        suite_xml=_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


class TestCrossPhaseInterstitialVariable:
    def test_module_level_storage_declared(self, run_host_match, ccpp_context):
        """The interstitial value gets real, correctly-typed module-scope
        storage in the generated suite cap -- not a throwaway per-call local."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        assert "integer, allocatable :: produced(:)" in fortran

    def test_allocated_before_producer_runs(self, run_host_match, ccpp_context):
        """The lazy-allocation guard appears, and precedes the call into the
        producing scheme (not after -- that would be the chained-ordering bug's
        own shape, not this one)."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        alloc_idx = fortran.index("if (.not. allocated(produced)) then")
        call_idx = fortran.index("call scheme_producer_run(")
        assert alloc_idx < call_idx

    def test_consumer_in_separate_phase_receives_same_storage(self, run_host_match, ccpp_context):
        """scheme_consumer_finalize is a genuinely separate generated
        subroutine from the one that produces the value (physics/_run) --
        confirms the module-level variable persists across the two separate
        calls without any explicit hand-off."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        assert "call scheme_consumer_finalize(consumed=produced" in fortran
