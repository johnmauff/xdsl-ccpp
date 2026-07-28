"""Unit tests for lifecycle_cap.py's _generate_lifecycle_fn resolving an
intent(inout) scalar host-matched to a DDT member -- a real runtime bug
found only by actually running examples/var_compat (this bug survives both
compilation and every existing FileCheck golden, since a fresh, uninitialized
local variable is still syntactically valid Fortran):

    ERROR in initialize of var_compatibility_suite:
    ERROR: effr_pre_init() needs to be called first

Root cause: effr_pre_init/effr_calc_init/effr_post_init/effr_diag_init all
take a shared intent(inout) `scheme_order` scalar (standard_name
scheme_order_in_suite) that HostVariableMatchPass correctly resolves to a
DDT member, phys_state%scheme_order -- test_host_data.F90 initializes it to
1 before physics_initialize runs, and each scheme's own _init checks it
against its expected call position, then increments it, relying on Fortran's
pass-by-reference semantics to thread the running count across the whole
call sequence.

_generate_lifecycle_fn's input-arg resolution loop only ever checked
"is this standard_name a plain MODULE-table variable" (host_var_map, built
with include_host=False) -- unlike run_dispatch.py's own "_run" dispatch,
it had no DDT-member resolution branch at all. A DDT-member match fell
through to the same "not host-matched" fallback used for genuinely
unmatched optional/allocatable args, allocating a fresh, uninitialized local
(`lc_scheme_order`) and passing that instead -- the host's real initial
value (1) was silently discarded, and each scheme's own init call operated
on a disconnected, garbage-valued local instead of the shared, persisted
counter.

Fixed by teaching _generate_lifecycle_fn the same DDT-member resolution
run_dispatch.py already has (via cap_shared.py's _build_ddt_resolution_maps/
_resolve_ddt_access_path/_resolve_member_subscripts, shared rather than
duplicated): the scheme-arg scan now also captures each arg's own
model_var_name/model_module_name/model_var_is_ddt (previously discarded,
only standard_name was kept), and the resolution loop tries DDT-member
resolution before falling back to a fresh local.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

_HOST_MOD_META = """\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
[ phys_state ]
  standard_name = physics_state_derived_type
  long_name = Physics State DDT
  type = phys_state_t
  dimensions = ()
"""

_HOST_DDT_META = """\
[ccpp-table-properties]
  name = phys_state_t
  type = ddt
[ccpp-arg-table]
  name = phys_state_t
  type = ddt
[ counter ]
  standard_name = call_order_counter
  units = count
  type = integer
  dimensions = ()
"""

_SCHEME_META = f"""\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
[ccpp-arg-table]
  name = scheme_a_init
  type = scheme
[ counter ]
  standard_name = call_order_counter
  units = count
  type = integer
  dimensions = ()
  intent = inout
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = scheme_a_run
  type = scheme
[ x ]
  standard_name = matched_scalar
  units = m
  type = real
  kind = kind_phys
  dimensions = ()
  intent = in
{CCPP_MANDATORY_ARGS}
"""

_HOST_MOD_META_WITH_MATCHED = _HOST_MOD_META + """\
[ x_host ]
  standard_name = matched_scalar
  units = m
  type = real
  kind = kind_phys
  dimensions = ()
"""


def _fortran_output(run_host_match, ccpp_context) -> str:
    module = run_host_match(
        scheme_metas=[_SCHEME_META],
        host_metas=[_HOST_MOD_META_WITH_MATCHED, _HOST_DDT_META],
        suite_xml=minimal_suite_xml("scheme_a"),
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fn_body(fortran: str, fn_name: str) -> str:
    return fortran.split(f"subroutine {fn_name}")[1].split(f"end subroutine {fn_name}")[0]


class TestLifecycleInitResolvesDDTMember:
    """scheme_a's _init entry declares an inout scalar (counter) host-matched
    to a DDT member (phys_state%counter) -- exactly var_compat's
    scheme_order shape."""

    def test_init_call_uses_real_ddt_member_not_fresh_local(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context)
        fn = _fn_body(fortran, "Test_ccpp_physics_initialize")
        call_line = next(
            line for line in fn.splitlines() if "call test_suite_suite_initialize" in line
        )
        assert "phys_state%counter" in call_line, (
            f"expected the real DDT member threaded into the call, got: {call_line!r}"
        )

    def test_no_fresh_uninitialized_local_declared(self, run_host_match, ccpp_context):
        """The actual runtime bug this fix closes: a fresh 'lc_counter'
        local was declared and passed instead of phys_state%counter,
        silently discarding whatever initial value the host had set."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        fn = _fn_body(fortran, "Test_ccpp_physics_initialize")
        assert "lc_counter" not in fn, (
            f"dead/wrong scratch local still declared and used:\n{fn}"
        )
