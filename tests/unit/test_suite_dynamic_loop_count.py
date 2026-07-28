"""Unit tests for resolving a dynamic (non-literal) subcycle loop count whose
standard_name has no matching scheme argument anywhere -- only a host
declaration.

Found via a real gfortran compile failure on examples/var_compat:
`do ccpp_loop_cnt1 = 1, num_subcycles_for_effr` -- but num_subcycles_for_effr
(the CCPP standard_name) is never declared anywhere in the generated file, no
scheme declares a matching arg of its own (unlike e.g. scheme_order_in_suite,
which flows through the ordinary scheme-arg host-matching path because
several schemes declare their own arg for it), so it never entered suite_cap.py's
all_args at all -- the raw standard_name string was printed directly as the
Fortran do-loop bound, which is not a valid identifier.

Fixed: suite_cap.py's _synthesize_dynamic_loop_count_args scans the suite's
subcycle structure for dynamic loop counts with no scheme-arg match, resolves
the host's own local name for the standard_name (scanning every non-scheme
host table, not just MODULE-type ones), and synthesizes a fresh HostMatched
CCPPArgument for it -- so it becomes a genuine, correctly-declared dummy
argument the same way any other host-matched value does. _emit_subcycle then
prints that argument's own name as the do-loop bound instead of the raw
standard_name.

This must only apply to the specific postfix (physics_mode=True, the "_run"
entry point) that actually emits a SubcycleLoopOp using it -- not every
lifecycle postfix the suite happens to have -- since a scheme can have both a
_run and an _init entry point, making the arg_tables-based check alone
insufficient (see _synthesize_dynamic_loop_count_args's own docstring).
"""

from io import StringIO

import pytest

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

_DYNAMIC_SUBCYCLE_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <subcycle loop="my_dynamic_count">
      <scheme>scheme_a</scheme>
      <scheme>scheme_b</scheme>
    </subcycle>
  </group>
</suite>
"""

_SCHEME_META = """\
[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_init
  type = scheme
{mandatory}
[ccpp-arg-table]
  name = {name}_run
  type = scheme
[ x ]
  standard_name = shared_var_{name}
  units = m
  type = real
  kind = kind_phys
  dimensions = ()
  intent = inout
{mandatory}
"""

_HOST_META = """\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
[ host_count ]
  standard_name = my_dynamic_count
  units = count
  type = integer
  dimensions = ()
"""

_HOST_META_NO_MATCH = """\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
[ unrelated_var ]
  standard_name = something_else_entirely
  units = 1
  type = integer
  dimensions = ()
"""


def _scheme_metas() -> list:
    return [
        _SCHEME_META.format(name="scheme_a", mandatory=CCPP_MANDATORY_ARGS),
        _SCHEME_META.format(name="scheme_b", mandatory=CCPP_MANDATORY_ARGS),
    ]


def _fortran_output(run_host_match, ccpp_context, host_metas) -> str:
    module = run_host_match(
        scheme_metas=_scheme_metas(), host_metas=host_metas,
        suite_xml=_DYNAMIC_SUBCYCLE_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fn_body(fortran: str, fn_name: str) -> str:
    return fortran.split(f"subroutine {fn_name}")[1].split(f"end subroutine {fn_name}")[0]


class TestDynamicLoopCountWithHostMatch:
    def test_do_loop_uses_hosts_own_local_name(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context, [_HOST_META])
        fn = _fn_body(fortran, "test_suite_suite_physics")
        assert any(
            "= 1, host_count" in line for line in fn.splitlines()
        ), f"expected a do-loop bound of host_count, got body:\n{fn}"
        assert "my_dynamic_count" not in fortran

    def test_declared_as_dummy_argument(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context, [_HOST_META])
        fn = _fn_body(fortran, "test_suite_suite_physics")
        assert any(
            "intent(in)" in line and ":: host_count" in line for line in fn.splitlines()
        )

    def test_not_added_to_unrelated_lifecycle_function(self, run_host_match, ccpp_context):
        """suite_initialize calls scheme_a_init/scheme_b_init -- both schemes
        ARE present in that postfix's own arg_tables (an arg_tables-only
        check would think the subcycle is "active" there too), but
        _init never runs under physics_mode, so it never emits a
        SubcycleLoopOp at all and must not gain host_count as an unused
        dummy argument."""
        fortran = _fortran_output(run_host_match, ccpp_context, [_HOST_META])
        fn = _fn_body(fortran, "test_suite_suite_initialize")
        assert "host_count" not in fn


class TestDynamicLoopCountWithoutHostMatch:
    def test_raises_clear_error(self, run_host_match, ccpp_context):
        with pytest.raises(ValueError, match="Subcycle loop count"):
            _fortran_output(run_host_match, ccpp_context, [_HOST_META_NO_MATCH])
