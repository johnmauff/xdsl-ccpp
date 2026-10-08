"""Regression coverage for `task65-interstitial-tests`' second gap:
non-`real` interstitial *array* verification.

The allocation scheduler (`LazyAllocOp`) is already confirmed kind-agnostic
by direct reading -- neither its own construction nor its printer
(`print_ftn.py`'s `CCPPLazyAllocOp` case) ever reads/branches on a kind
name; declaration-type formatting is handled entirely by `_build_module_vars`
(`suite_cap.py`), which already branches generically on `entry.fortran_type`.
`tests/unit/test_interstitial_variable.py` already proves this end-to-end
for an `integer` interstitial array; this file fills in the two kinds that
were otherwise completely unexercised through this path: `logical` and
`character`. Deliberately mirrors that file's own producer/consumer/host
fixture shape exactly, swapping only the declared type -- these two new
classes only need to prove kind-generality (declaration + allocation
ordering), not re-prove the cross-phase hand-off `test_interstitial_variable.py`
already covers once.
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


def _fortran_output(run_host_match, ccpp_context, scheme_producer_meta, scheme_consumer_meta) -> str:
    module = run_host_match(
        scheme_metas=[scheme_producer_meta, scheme_consumer_meta],
        host_metas=[_HOST_META],
        suite_xml=_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


_LOGICAL_PRODUCER_META = f"""\
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
  type = logical
  dimensions = (horizontal_dimension)
  intent = out
{CCPP_MANDATORY_ARGS}
"""

_LOGICAL_CONSUMER_META = f"""\
[ccpp-table-properties]
  name = scheme_consumer
  type = scheme
[ccpp-arg-table]
  name = scheme_consumer_finalize
  type = scheme
[ consumed ]
  standard_name = my_interstitial_value
  units = 1
  type = logical
  dimensions = (horizontal_dimension)
  intent = in
{CCPP_MANDATORY_ARGS}
"""

_CHARACTER_PRODUCER_META = f"""\
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
  type = character
  kind = len=32
  dimensions = (horizontal_dimension)
  intent = out
{CCPP_MANDATORY_ARGS}
"""

_CHARACTER_CONSUMER_META = f"""\
[ccpp-table-properties]
  name = scheme_consumer
  type = scheme
[ccpp-arg-table]
  name = scheme_consumer_finalize
  type = scheme
[ consumed ]
  standard_name = my_interstitial_value
  units = 1
  type = character
  kind = len=32
  dimensions = (horizontal_dimension)
  intent = in
{CCPP_MANDATORY_ARGS}
"""


class TestLogicalInterstitialArray:
    def test_module_level_storage_declared(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context, _LOGICAL_PRODUCER_META, _LOGICAL_CONSUMER_META,
        )
        assert "logical, allocatable :: produced(:)" in fortran

    def test_allocated_before_producer_runs(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context, _LOGICAL_PRODUCER_META, _LOGICAL_CONSUMER_META,
        )
        alloc_idx = fortran.index("if (.not. allocated(produced)) then")
        call_idx = fortran.index("call scheme_producer_run(")
        assert alloc_idx < call_idx


class TestCharacterInterstitialArray:
    def test_module_level_storage_declared(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context, _CHARACTER_PRODUCER_META, _CHARACTER_CONSUMER_META,
        )
        assert "character(len=32), allocatable :: produced(:)" in fortran

    def test_allocated_before_producer_runs(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context, _CHARACTER_PRODUCER_META, _CHARACTER_CONSUMER_META,
        )
        alloc_idx = fortran.index("if (.not. allocated(produced)) then")
        call_idx = fortran.index("call scheme_producer_run(")
        assert alloc_idx < call_idx
