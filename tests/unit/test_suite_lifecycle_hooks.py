"""Unit tests for suite-level <init>/<final> scheme hooks (v2.0 SDF schema).

Backlog item: `nested_suite` in ccpp_cap_refactor_plan.md. Ported from
reading NCAR ccpp-framework's real feature/capgen-v1 source directly
(capgen/generator/suite_resolver.py's suite-level <init>/<final> resolution,
suite_cap.py's _init_lines/_final_lines call emission), not guessed from the
SDF v2.0 schema alone -- confirmed against the real end-to-end-tests/
nested_suite example's own suite_lifecycle.F90 (a scheme with only init/
final entry points, incrementing a shared counter; the test's own pass
condition is exactly counter == 2).

A suite may declare a single <init>/<final> scheme name as a direct child
(not inside any group), called once per suite lifecycle rather than once
per group. Note the entry-point postfix is "_init"/"_final" -- matching the
tag names themselves, NOT this codebase's own group-scheme "_finalize"
convention (confirmed against suite_lifecycle.F90's own subroutine names).
"""

from io import StringIO

import pytest

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

_LIFECYCLE_SCHEME_META = """\
[ccpp-table-properties]
  name = lifecycle_scheme
  type = scheme
[ccpp-arg-table]
  name = lifecycle_scheme_init
  type = scheme
[ counter ]
  standard_name = lifecycle_counter
  units = 1
  dimensions = ()
  type = integer
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
[ccpp-arg-table]
  name = lifecycle_scheme_final
  type = scheme
[ counter ]
  standard_name = lifecycle_counter
  units = 1
  dimensions = ()
  type = integer
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

_INIT_ONLY_SCHEME_META = """\
[ccpp-table-properties]
  name = init_only_scheme
  type = scheme
[ccpp-arg-table]
  name = init_only_scheme_init
  type = scheme
[ counter ]
  standard_name = lifecycle_counter
  units = 1
  dimensions = ()
  type = integer
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

_SCHEME_A_META = f"""\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
[ccpp-arg-table]
  name = scheme_a_run
  type = scheme
{CCPP_MANDATORY_ARGS}
"""

_HOST_META = """\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
[ lifecycle_counter ]
  standard_name = lifecycle_counter
  units = 1
  dimensions = ()
  type = integer
"""

_SUITE_XML_WITH_HOOKS = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="2.0">
  <init>lifecycle_scheme</init>
  <group name="g1">
    <scheme>scheme_a</scheme>
  </group>
  <final>lifecycle_scheme</final>
</suite>
"""

_SUITE_XML_NO_HOOKS = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="2.0">
  <group name="g1">
    <scheme>scheme_a</scheme>
  </group>
</suite>
"""

_SUITE_XML_INIT_ONLY_MISSING_FINAL_PHASE = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="2.0">
  <init>init_only_scheme</init>
  <group name="g1">
    <scheme>scheme_a</scheme>
  </group>
  <final>init_only_scheme</final>
</suite>
"""


def _fortran_output(run_host_match, ccpp_context, scheme_metas, suite_xml) -> str:
    module = run_host_match(
        scheme_metas=scheme_metas, host_metas=[_HOST_META], suite_xml=suite_xml,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fn_body(fortran: str, fn_name: str) -> str:
    return fortran.split(f"subroutine {fn_name}")[1].split(f"end subroutine {fn_name}")[0]


class TestSuiteLifecycleHooksEmitCallsInTheRightSubroutines:
    def test_init_call_in_suite_initialize_only(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_LIFECYCLE_SCHEME_META, _SCHEME_A_META], _SUITE_XML_WITH_HOOKS,
        )
        init_fn = _fn_body(fortran, "test_suite_suite_initialize")
        assert (
            "call lifecycle_scheme_init(counter=lifecycle_counter, "
            "errmsg=errmsg, errflg=errflg)"
        ) in init_fn

        # Not spuriously called anywhere else. test_suite_suite_timestep_init_g1
        # (task #28: timestep_init is now group-scoped), not the old flat
        # test_suite_suite_timestep_initial.
        for other_fn_name in (
            "test_suite_suite_timestep_init_g1",
            "test_suite_suite_timestep_final",
            "test_suite_suite_g1",
        ):
            assert "lifecycle_scheme_init" not in _fn_body(fortran, other_fn_name)

    def test_final_call_in_suite_finalize_only(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_LIFECYCLE_SCHEME_META, _SCHEME_A_META], _SUITE_XML_WITH_HOOKS,
        )
        final_fn = _fn_body(fortran, "test_suite_suite_finalize")
        assert (
            "call lifecycle_scheme_final(counter=lifecycle_counter, "
            "errmsg=errmsg, errflg=errflg)"
        ) in final_fn

        # test_suite_suite_timestep_init_g1 (task #28: timestep_init is now
        # group-scoped), not the old flat test_suite_suite_timestep_initial.
        for other_fn_name in (
            "test_suite_suite_initialize",
            "test_suite_suite_timestep_init_g1",
            "test_suite_suite_timestep_final",
            "test_suite_suite_g1",
        ):
            assert "lifecycle_scheme_final" not in _fn_body(fortran, other_fn_name)

    def test_use_stub_and_host_var_correctly_emitted(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_LIFECYCLE_SCHEME_META, _SCHEME_A_META], _SUITE_XML_WITH_HOOKS,
        )
        assert "use lifecycle_scheme, only: lifecycle_scheme_init" in fortran
        assert "use lifecycle_scheme, only: lifecycle_scheme_final" in fortran
        assert "use test_host_mod, only: lifecycle_counter" in fortran
        # Deduplicated across init+final referencing the same host var, not doubled.
        assert fortran.count("use test_host_mod, only: lifecycle_counter") == 1


class TestSuiteWithoutHooksUnaffected:
    """A suite declaring no <init>/<final> must not gain any spurious call --
    confirms the whole feature is a strict no-op when unused."""

    def test_no_lifecycle_call_anywhere(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context, [_SCHEME_A_META], _SUITE_XML_NO_HOOKS,
        )
        assert "lifecycle_scheme" not in fortran


class TestMissingPhaseRaisesClearError:
    """<final>init_only_scheme</final> but init_only_scheme has no _final
    phase in its own metadata -- must raise a clear, specific error rather
    than an opaque KeyError/AttributeError deep in call construction."""

    def test_raises_clear_error(self, run_host_match, ccpp_context):
        with pytest.raises(ValueError, match="init_only_scheme.*no '_final' phase"):
            _fortran_output(
                run_host_match, ccpp_context,
                [_INIT_ONLY_SCHEME_META, _SCHEME_A_META],
                _SUITE_XML_INIT_ONLY_MISSING_FINAL_PHASE,
            )


_UNMATCHED_ARG_SCHEME_META = """\
[ccpp-table-properties]
  name = unmatched_arg_scheme
  type = scheme
[ccpp-arg-table]
  name = unmatched_arg_scheme_init
  type = scheme
[ nothing_host_declares ]
  standard_name = totally_unmatched_standard_name
  units = 1
  dimensions = ()
  type = integer
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

_SUITE_XML_UNMATCHED_ARG = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="2.0">
  <init>unmatched_arg_scheme</init>
  <group name="g1">
    <scheme>scheme_a</scheme>
  </group>
</suite>
"""


class TestUnmatchedHookArgRaisesClearErrorWithNoTypo:
    """Found by Copilot's review of PR #47: the "no host match" error
    message had a stray extra quote right after scheme_name (an awkward
    doubled quote in the rendered message), left over from an earlier
    possessive-with-quotes phrasing. Also confirms the error path itself
    (a suite-level hook scheme arg no host anywhere matches) is reachable
    and reports clearly rather than crashing deeper in call construction."""

    def test_error_message_has_no_doubled_quote(self, run_host_match, ccpp_context):
        with pytest.raises(ValueError) as excinfo:
            _fortran_output(
                run_host_match, ccpp_context,
                [_UNMATCHED_ARG_SCHEME_META, _SCHEME_A_META],
                _SUITE_XML_UNMATCHED_ARG,
            )
        message = str(excinfo.value)
        assert "''s" not in message, message
        assert "unmatched_arg_scheme' has arg 'nothing_host_declares'" in message
