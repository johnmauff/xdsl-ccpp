"""Unit tests for a real ifx compile failure on examples/var_compat, found
only by an actual standards-strict compiler -- gfortran accepts the
offending Fortran, and every existing FileCheck golden matched it
byte-for-byte, so this survived undetected until a real build was tried:

    error #5192: Lead underscore not allowed
              num_subcycles=phys_state%num_subcycles, _out_0=ccpp_tmp_0, ...
    error #6784: The number of actual arguments cannot be greater than the
                 number of dummy arguments.
    error #6627: This is an actual argument keyword name, and not a dummy
                 argument name.   [_OUT_0]

Root cause, one layer deeper than either symptom: run_dispatch.py's
_build_run_dispatch_chain has no copy-back branch at all for a suite
callee's own leading intent(inout) SCALAR return value when it's
host-matched to a DDT member (e.g. var_compat's scalar_var/tke_inout/
tke2_inout, resolved to phys_state%scalar_var) rather than a plain
caller-block argument or a plain host/cap-owned module variable -- the
existing block_arg_map / host_var_map / cap_var_map branches all miss it.
With no CopyOp consumer at all, print_ftn.py's own "untracked call result"
fallback (_has_copy_consumer) takes over: it invents a throwaway
"ccpp_tmp_N" local for the value and, in the PLAIN POSITIONAL-call path
(TestPositionalCallGetsNoExtraArgument below), prints it as a genuine EXTRA
positional argument -- a real arity mismatch that also silently shifts
every later positional argument (including errmsg/errflg) into the wrong
dummy-argument slot. In the KEYWORD-call path (used whenever any of the
suite's own inputs is optional, so Fortran correctly forwards OPTIONAL
absence status -- TestDDTMemberInoutScalarGetsRealKeywordName below), the
same untracked value additionally got a synthetic "_out_{i}" placeholder
keyword name from a separate, earlier list comprehension that only
recognized errmsg/errflg by type -- invalid Fortran on two counts: the
leading underscore (not a legal Fortran identifier start) and the
resulting arity mismatch (an extra keyword bound to nothing the callee
declares).

Fixed with two complementary changes:
  1. A new copy-back branch reuses the exact same HostVarRefOp already
     built as this argument's own INPUT reference (host_var_ref_results,
     populated once per callee arg before the call is built) as the
     copy-back target too -- functionally a no-op (Fortran already
     reflects the update through the same aliased reference), but it gives
     the result a real CopyOp consumer, so it never reaches the
     untracked-call-result fallback in the first place. This alone fixes
     the positional-call arity bug and eliminates the dead "ccpp_tmp_N"
     declaration entirely (not just its use).
  2. The keyword-call path's result-name construction was moved after (and
     now reuses) the same leading-inout/trailing-alloc classification the
     copy-back loop uses, computing each output position's REAL callee
     dummy-argument name instead of a synthetic "_out_{i}" placeholder --
     belt-and-suspenders alongside fix 1, and the only thing needed for
     positions fix 1 doesn't cover (e.g. a genuine trailing alloc-region
     scalar with no operand-side entry at all, which legitimately does
     need its own real keyword name printed).
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
[ y ]
  standard_name = shared_inout_scalar
  units = m
  type = real
  kind = kind_phys
  dimensions = ()
"""

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


_SCHEME_META_NO_OPTIONAL = f"""\
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
{CCPP_MANDATORY_ARGS}
"""


def _fortran_output(run_host_match, ccpp_context, scheme_meta=_SCHEME_META) -> str:
    module = run_host_match(
        scheme_metas=[scheme_meta],
        host_metas=[_HOST_MOD_META, _HOST_DDT_META],
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


class TestDDTMemberInoutScalarGetsRealKeywordName:
    """scheme_a's inout scalar "y" is host-matched to a DDT member
    (phys_state%y), and scheme_a also declares an optional arg (z_opt) --
    forcing the wrapper's dispatch to use a KeywordCallOp rather than a
    plain positional call. This is exactly var_compat's real
    scalar_var/tke_inout/tke2_inout shape."""

    def test_no_synthetic_out_n_placeholder_anywhere(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context)
        assert "_out_" not in fortran, (
            f"synthetic placeholder keyword leaked into generated Fortran:\n{fortran}"
        )

    def test_no_leading_underscore_identifiers(self, run_host_match, ccpp_context):
        """Direct regression for ifx's own diagnostic ("Lead underscore not
        allowed") -- gfortran accepts this non-standard form, so only a
        strict-standards compiler catches it; assert the general property
        instead of just the one placeholder spelling."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        fn = _fn_body(fortran, "Test_ccpp_physics_run")
        call_line = next(
            line for line in fn.splitlines() if "call test_suite_suite_physics" in line
        )
        keywords = [
            a.strip().split("=", 1)[0]
            for a in call_line.split("(", 1)[1].rsplit(")", 1)[0].split(",")
        ]
        for kw in keywords:
            assert not kw.startswith("_"), f"illegal leading-underscore keyword: {kw!r}"

    def test_y_bound_exactly_once_under_its_real_name(self, run_host_match, ccpp_context):
        """The actual arity-mismatch bug this fix closes: without it, "y"
        would be bound twice -- once correctly (y=phys_state%y) and once
        under the bogus "_out_N=ccpp_tmp_N" keyword the callee's own
        signature never declares."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        fn = _fn_body(fortran, "Test_ccpp_physics_run")
        call_line = next(
            line for line in fn.splitlines() if "call test_suite_suite_physics" in line
        )
        args = [
            a.strip()
            for a in call_line.split("(", 1)[1].rsplit(")", 1)[0].split(",")
        ]
        y_bindings = [a for a in args if a == "y=phys_state%y"]
        assert len(y_bindings) == 1, f"expected 'y' bound exactly once, got: {call_line!r}"

    def test_call_arg_count_matches_callee_signature(self, run_host_match, ccpp_context):
        """Direct regression for ifx's own #6784 ("number of actual arguments
        cannot be greater than the number of dummy arguments")."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        callee_sig = fortran.split("subroutine test_suite_suite_physics(")[1].split(")")[0]
        n_dummy_args = len([a for a in callee_sig.split(",") if a.strip()])
        fn = _fn_body(fortran, "Test_ccpp_physics_run")
        call_line = next(
            line for line in fn.splitlines() if "call test_suite_suite_physics" in line
        )
        n_actual_args = len(
            [a for a in call_line.split("(", 1)[1].rsplit(")", 1)[0].split(",") if a.strip()]
        )
        assert n_actual_args == n_dummy_args, (
            f"actual arg count {n_actual_args} != dummy arg count {n_dummy_args}: "
            f"{call_line!r}"
        )


class TestPositionalCallGetsNoExtraArgument:
    """Same DDT-member-resolved inout scalar "y", but scheme_a declares no
    optional arg here, so the wrapper dispatches via a plain positional
    func.CallOp rather than a KeywordCallOp -- the more serious of the two
    symptoms: print_ftn.py's positional-call printer has no name-based
    dedup at all (only a value-based one, matching by resolved variable
    text), so an untracked result there doesn't just print an oddly-named
    extra keyword -- it prints an entirely unnamed extra POSITIONAL
    argument, silently shifting every later argument (including errmsg/
    errflg) into the wrong dummy-argument slot."""

    def test_call_has_exactly_the_callees_own_arg_count(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context, _SCHEME_META_NO_OPTIONAL)
        callee_sig = fortran.split("subroutine test_suite_suite_physics(")[1].split(")")[0]
        n_dummy_args = len([a for a in callee_sig.split(",") if a.strip()])
        fn = _fn_body(fortran, "Test_ccpp_physics_run")
        call_line = next(
            line for line in fn.splitlines() if "call test_suite_suite_physics" in line
        )
        n_actual_args = len(
            [a for a in call_line.split("(", 1)[1].rsplit(")", 1)[0].split(",") if a.strip()]
        )
        assert n_actual_args == n_dummy_args, (
            f"actual arg count {n_actual_args} != dummy arg count {n_dummy_args} "
            f"(an extra untracked-result argument would silently shift errmsg/"
            f"errflg into the wrong dummy-argument slot): {call_line!r}"
        )

    def test_call_args_are_exactly_y_errmsg_errflg_in_order(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context, _SCHEME_META_NO_OPTIONAL)
        fn = _fn_body(fortran, "Test_ccpp_physics_run")
        call_line = next(
            line for line in fn.splitlines() if "call test_suite_suite_physics" in line
        )
        args = [
            a.strip()
            for a in call_line.split("(", 1)[1].rsplit(")", 1)[0].split(",")
        ]
        assert args == ["phys_state%y", "errmsg", "errflg"], (
            f"unexpected positional call arguments: {call_line!r}"
        )

    def test_no_dead_ccpp_tmp_local_declared(self, run_host_match, ccpp_context):
        """The root-cause fix (a real copy-back consumer for the DDT-member
        result) means print_ftn.py's untracked-call-result fallback is never
        triggered at all -- not just suppressed at print time. No throwaway
        local should be declared in the wrapper any more."""
        fortran = _fortran_output(run_host_match, ccpp_context, _SCHEME_META_NO_OPTIONAL)
        fn = _fn_body(fortran, "Test_ccpp_physics_run")
        assert "ccpp_tmp" not in fn, f"dead throwaway local still declared:\n{fn}"
