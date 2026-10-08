"""Regression coverage for `task65-interstitial-tests`' first gap:
DDT-typed interstitial *declaration* coverage.

`suite_cap.py`'s `_build_module_vars` has a dedicated `entry.is_ddt`
branch -- a DDT-typed SuiteOwned ("interstitial") variable is declared as
a module-scope, non-allocatable scalar (`type(ddt_name) :: var`, always
rank=0, never routed through the LazyAllocOp allocation scheduler, since
`SuiteVariableModel.needs_allocation()` returns False whenever
`entry.is_ddt` is True). This path was confirmed "genuinely untested, not
just unverified" in task #65's own 2026-08-20 scoping note -- no example
or existing test constructs the one shape that reaches it: a
non-allocatable, intent(out), DDT-typed scheme arg with no host-table
match (the ordinary interstitial/SuiteOwned classification rule, just
with a DDT type name instead of a primitive one).

`my_ddt_type` below is a synthetic, non-framework DDT name chosen
specifically so the printer's automatic DDT `use`-association logic
(hardcoded framework-DDT table, or a real function block argument) never
fires for it -- this test only asserts on the declaration/no-allocation
shape, not on any `use` line.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

_SUITE_XML = minimal_suite_xml("scheme_producer")

_SCHEME_META = f"""\
[ccpp-table-properties]
  name = scheme_producer
  type = scheme
[ccpp-arg-table]
  name = scheme_producer_run
  type = scheme
[ produced ]
  standard_name = my_ddt_interstitial_value
  units = none
  type = my_ddt_type
  dimensions = ()
  intent = out
{CCPP_MANDATORY_ARGS}
"""

_HOST_META = """\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
"""


def _fortran_output(run_host_match, ccpp_context) -> str:
    module = run_host_match(
        scheme_metas=[_SCHEME_META], host_metas=[_HOST_META], suite_xml=_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


class TestDdtInterstitialDeclaration:
    def test_declared_as_nonallocatable_scalar(self, run_host_match, ccpp_context):
        """A DDT-typed interstitial gets a plain type(...) module-scope
        declaration -- no `allocatable` qualifier, matching real Fortran's
        own restriction (a derived-type interstitial has no dimensions to
        defer, so there's nothing for `allocatable` to apply to)."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        decl_line = next(l for l in fortran.splitlines() if "type(my_ddt_type) ::" in l)
        assert "produced" in decl_line
        assert "allocatable" not in decl_line

    def test_never_allocated(self, run_host_match, ccpp_context):
        """No lazy-allocation guard is ever emitted for a DDT interstitial
        -- SuiteVariableModel.needs_allocation() exempts is_ddt entries
        unconditionally, so neither an allocate() call nor an
        allocated(...) guard should appear anywhere in the output."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        assert "allocate(produced" not in fortran
        assert "allocated(produced)" not in fortran
