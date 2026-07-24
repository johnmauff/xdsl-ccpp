"""Unit tests for the combined ccpp_cap physics_run wrapper's own declared
intent on an ordinary scheme-declared intent=inout scalar with no dedicated
framework meaning of its own (no persisted host module storage, not
ccpp_error_message/ccpp_error_code, not a ccpp_t handle) -- e.g.
examples/var_compat's scalar_var/tke_inout/tke2_inout.

Found via a real gfortran compile failure on examples/var_compat:
VarCompatibility_ccpp_physics_run declared scalar_var/tke_inout intent(in)
while the suite subroutine it calls (var_compatibility_suite_suite_radiation)
correctly declares them intent(inout) -- passing an intent(in) actual
argument into an intent(inout) dummy argument is invalid Fortran.

Root cause: run_dispatch.py's _build_run_dispatch_chain has a copy-back loop
for the suite callee's own leading (inout-position) return values, but it
only ever special-cased three framework things: ccpp_error_message,
ccpp_error_code, and a ccpp_t handle. An ordinary scheme-declared inout
scalar in that same leading region had no copy-back at all, so the value
never made it back to the wrapper's own block argument, and print_ftn.py
(which declares a scalar dummy argument intent(inout) only when it appears
in the function's own ReturnOp) always saw it as intent(in).

Fixed by a new _get_suite_leading_inout_ret_info helper (cap_shared.py) that
name-resolves this leading-region case (mirroring the pre-existing
_get_suite_lifecycle_ret_info helper's own resolution of the trailing
alloc-region case), plus recording the echoed block arg so
_assemble_run_fn's own ReturnOp includes it too -- which is what makes the
printer declare it intent(inout) at the wrapper level, matching the callee.

That fix in turn exposed a second, closely related bug in print_ftn.py's
_print_kw_call: once the copy-back target is the SAME variable already
passed in as an input (the common case here, since this scalar has no
persisted host storage and flows straight through as a caller-supplied
block argument), the printer must suppress the synthetic "_out_N=" echo it
would otherwise print -- printing the same variable under two different
keyword names bound to what is really the same dummy argument is also
invalid Fortran. The positional-call printer (_print_call) already had this
suppression; _print_kw_call needed a matching value-based fix
(TestNoDuplicateKeywordArg below).

The [ y_host ] entry in _HOST_META below (a HOST-type, not MODULE-type,
table declaration) is what keeps "y" a genuine passthrough block argument
instead of being promoted to a cap-owned module variable (ArgOwnershipKind.
CapScratch) -- see cap_shared.py's classify_arg_ownership and
_collect_host_block_std_names docstrings: a HOST-type table entry marks a
standard_name as "caller provides this each call, no persisted storage,"
independently of whether HostVariableMatchPass finds any real MODULE/DDT
match for it (it finds none here). This mirrors examples/var_compat's own
test_host.meta HOST-type table exactly.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

_SCHEME_META = f"""\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
[ccpp-arg-table]
  name = scheme_a_run
  type = scheme
[ y ]
  standard_name = shared_inout_scalar
  units = m
  type = real
  kind = kind_phys
  dimensions = ()
  intent = inout
[ z_opt ]
  standard_name = unused_optional_scalar
  units = m
  type = real
  kind = kind_phys
  dimensions = ()
  intent = in
  optional = True
{CCPP_MANDATORY_ARGS}
"""

_HOST_META = """\
[ccpp-table-properties]
  name = test_host
  type = host
[ccpp-arg-table]
  name = test_host
  type = host
[ y_host ]
  standard_name = shared_inout_scalar
  units = m
  type = real
  kind = kind_phys
  dimensions = ()
"""


def _fortran_output(run_host_match, ccpp_context) -> str:
    module = run_host_match(
        scheme_metas=[_SCHEME_META], host_metas=[_HOST_META],
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


class TestWrapperDeclaresInoutScalarInout:
    def test_wrapper_declares_intent_inout(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context)
        fn = _fn_body(fortran, "Test_ccpp_physics_run")
        decl = next(line for line in fn.splitlines() if ":: y" in line)
        assert "intent(inout)" in decl, f"expected intent(inout), got: {decl!r}"

    def test_suite_callee_also_declares_intent_inout(self, run_host_match, ccpp_context):
        # Sanity check: the suite subroutine itself must agree (already
        # covered by test_suite_scalar_inout_intent.py, but confirms the two
        # bugs are being observed against the same argument).
        fortran = _fortran_output(run_host_match, ccpp_context)
        fn = _fn_body(fortran, "test_suite_suite_physics")
        decl = next(line for line in fn.splitlines() if ":: y" in line)
        assert "intent(inout)" in decl, f"expected intent(inout), got: {decl!r}"


class TestNoDuplicateKeywordArg:
    def test_y_appears_exactly_once_in_the_call(self, run_host_match, ccpp_context):
        """Regression for print_ftn.py's _print_kw_call: once y's copy-back
        target is the same variable already passed as an input, the
        synthetic "_out_N=y" echo must be suppressed -- printing y twice
        under two different keyword names bound to the same dummy argument
        is invalid Fortran."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        fn = _fn_body(fortran, "Test_ccpp_physics_run")
        call_line = next(
            line for line in fn.splitlines() if "call test_suite_suite_physics" in line
        )
        args = [
            a.strip()
            for a in call_line.split("(", 1)[1].rsplit(")", 1)[0].split(",")
        ]
        y_bindings = [a for a in args if a == "y" or a.endswith("=y")]
        assert len(y_bindings) == 1, f"expected 'y' bound exactly once, got: {call_line!r}"
        assert "_out_0" not in fn
