"""Unit tests for ccpp_cap.py's _build_suite_variables_fn -- three real gaps
found via an actual runtime failure on examples/var_compat, only caught once
the example finally built and ran (test_host.F90's own check_suite() calls
ccpp_physics_suite_variables and compares against hardcoded expected counts):

    ERROR: Found 16 input variable names for suite, var_compatibility_suite,
           should be 18
    ERROR: Found 15 output variable names for suite, var_compatibility_suite,
           should be 14
    ERROR: Found 21 required variable names for suite, var_compatibility_suite,
           should be 22

Three independent gaps, each covered by its own test class below:

1. TestOptionalUnmatchedCapScratchExcluded -- an optional intent=out scheme
   arg with no host match at all (var_compat's ncl_out/
   cloud_liquid_number_concentration) resolves to a throwaway cap-owned
   scratch variable that never reaches the host in either direction, so it
   must not appear in the suite's variable list -- it was being included
   unconditionally by declared intent alone.

2. TestDynamicSubcycleLoopCountIncluded -- a dynamic (non-literal) subcycle
   loop count (var_compat's num_subcycles_for_effr) is synthesized directly
   by suite_cap.py's _synthesize_dynamic_loop_count_args and never becomes a
   real scheme-table ArgumentOp anywhere, so the scheme-table scan in
   _build_suite_variables_fn had no way to discover it, even though the host
   must genuinely supply it.

3. TestActiveExpressionReferenceIncluded -- a standard_name referenced only
   inside an `active = (...)` conditional-presence expression on a host/DDT
   variable (var_compat's flag_indicating_cloud_microphysics_has_ice) is
   never itself a scheme argument, so it was never discovered either, even
   though the host must genuinely supply it.

Fix (1) turned out to need two additional guards beyond "CapScratch and not
a recognized framework array with no host declaration", discovered via
regressions caught by the full repo test suite (not synthesized here as unit
tests, since they'd duplicate existing FileCheck golden coverage that already
locks in the fix):
  - Guard against "no host files supplied to this invocation at all" (every
    scheme var looks CapScratch then, regardless of whether a real host
    would match it) -- see TestNoHostFilesAtAllNeverExcludes.
  - Guard against mandatory (non-optional) CapScratch args, which represent
    a genuine suite requirement (an interstitial value, or a constituent
    array) rather than a silently-droppable scratch value -- see
    TestMandatoryCapScratchNeverExcluded.

Fix (3) is additionally scoped to modules with exactly one suite (see
TestActiveExpressionReferenceIncluded's own class docstring) -- a
multi-suite-module regression is covered by the existing
tests/filecheck/examples/{completed_ir,end_to_end}/capgen-xml.mlir goldens
(capgen generates two suites, ddt_suite and temp_suite, from one invocation
sharing a host file with exactly this active= pattern) rather than
duplicated here, since building a two-suite fixture through this file's
existing test scaffolding would need extending it well beyond this fix's
own scope.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.suite_cap import SuiteCAP
from xdsl_ccpp.transforms.suite_meta import MetaCAP


def _fortran_output(
    run_host_match, ccpp_context, scheme_metas, host_metas,
    scheme_name="scheme_a", suite_xml=None,
) -> str:
    module = run_host_match(
        scheme_metas=scheme_metas,
        host_metas=host_metas,
        suite_xml=suite_xml if suite_xml is not None else minimal_suite_xml(scheme_name),
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _suite_variables_body(fortran: str) -> str:
    return fortran.split("subroutine ccpp_physics_suite_variables")[1].split(
        "end subroutine ccpp_physics_suite_variables"
    )[0]


class TestOptionalUnmatchedCapScratchExcluded:
    """scheme_a's "unused_out" arg is optional, intent=out, and its
    standard_name is declared nowhere in the (real, non-empty) host
    metadata -- exactly var_compat's ncl_out/
    cloud_liquid_number_concentration shape."""

    _SCHEME_META = f"""\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
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
[ unused_out ]
  standard_name = unmatched_optional_output
  units = m
  type = real
  kind = kind_phys
  dimensions = ()
  intent = out
  optional = True
{CCPP_MANDATORY_ARGS}
"""

    _HOST_META = """\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
[ x_host ]
  standard_name = matched_scalar
  units = m
  type = real
  kind = kind_phys
  dimensions = ()
"""

    def test_unmatched_optional_output_not_in_output_list(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context, [self._SCHEME_META], [self._HOST_META]
        )
        body = _suite_variables_body(fortran)
        assert "unmatched_optional_output" not in body, (
            f"excluded var leaked into suite_variables:\n{body}"
        )

    def test_matched_scalar_still_present(self, run_host_match, ccpp_context):
        """Sanity check: the fix doesn't over-exclude -- a genuinely
        host-matched var must still appear."""
        fortran = _fortran_output(
            run_host_match, ccpp_context, [self._SCHEME_META], [self._HOST_META]
        )
        body = _suite_variables_body(fortran)
        assert "matched_scalar" in body


class TestNoHostFilesAtAllNeverExcludes:
    """Same optional, unmatched arg as above, but with NO host metadata
    supplied at all (an empty host_metas list, matching how
    tests/filecheck/examples/end_to_end/helloworld-xml.mlir deliberately
    omits --host-files to exercise the scheme-only frontend path).

    Confirmed via examples/helloworld's own hello_world_mod.meta, which
    genuinely does declare a host match for the variable that test exercises
    -- only that specific host-less invocation makes it look unmatched.
    Without this guard, a host-less invocation would incorrectly drop every
    optional scheme arg from the list, not just genuinely-unmatched ones."""

    _SCHEME_META = f"""\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
[ccpp-arg-table]
  name = scheme_a_run
  type = scheme
[ unused_out ]
  standard_name = unmatched_optional_output
  units = m
  type = real
  kind = kind_phys
  dimensions = ()
  intent = out
  optional = True
{CCPP_MANDATORY_ARGS}
"""

    def test_still_present_when_no_host_files_supplied(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context, [self._SCHEME_META], []
        )
        body = _suite_variables_body(fortran)
        assert "unmatched_optional_output" in body, (
            f"var wrongly excluded with no host context at all:\n{body}"
        )


class TestMandatoryCapScratchNeverExcluded:
    """Same shape as TestOptionalUnmatchedCapScratchExcluded, but
    "mandatory_out" is NOT optional -- a mandatory arg with no host match
    represents a real suite requirement (a constituent array like
    examples/advection's own tendency_of_cloud_liquid_dry_mixing_ratio,
    which _build_cap_var_map's own docstring names as an intentional
    CapScratch example that must still appear in this list) -- only an
    optional arg can be silently absent, which is what makes exclusion safe
    for that case and not this one.

    Deliberately skips HostVariableMatchPass (unlike every other test class
    here, which uses the run_host_match fixture): an unmatched intent=out
    arg with no other consumer gets marked is_interstitial by that pass on
    its own (a real, pre-existing, unrelated mechanism -- SuiteOwned via
    is_interstitial, not CapScratch, is excluded via interstitial_std_names
    long before this fix's own check even runs), which would make this
    fixture a no-op test of the wrong thing. examples/advection's own
    end-to-end FileCheck golden hits the *actual* mandatory-CapScratch case
    this guards against for exactly this same structural reason: its test
    pipeline never runs generate-host-match at all (confirmed via its own
    RUN line), so is_interstitial is never set on tcld/cld_liq_tend, which
    fall through to genuine CapScratch classification instead -- this test
    mirrors that same reduced pipeline rather than the fixture default."""

    _SCHEME_META = f"""\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
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
[ mandatory_out ]
  standard_name = unmatched_mandatory_output
  units = m
  type = real
  kind = kind_phys
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
[ x_host ]
  standard_name = matched_scalar
  units = m
  type = real
  kind = kind_phys
  dimensions = ()
"""

    def test_mandatory_unmatched_output_still_present(self, build_module, ccpp_context):
        module = build_module(
            scheme_metas=[self._SCHEME_META],
            host_metas=[self._HOST_META],
            suite_xml=minimal_suite_xml("scheme_a"),
        )
        MetaCAP().apply(ccpp_context, module)
        # No HostVariableMatchPass -- see class docstring.
        ArgOwnershipPass().apply(ccpp_context, module)
        SuiteCAP().apply(ccpp_context, module)
        CCPPCAP().apply(ccpp_context, module)
        out = StringIO()
        print_to_ftn(module, out)
        body = _suite_variables_body(out.getvalue())
        assert "unmatched_mandatory_output" in body, (
            f"mandatory unmatched var wrongly excluded:\n{body}"
        )


class TestDynamicSubcycleLoopCountIncluded:
    """A `<subcycle loop="dynamic_loop_count">` around scheme_a's own call --
    dynamic_loop_count is never declared as any scheme's own arg (it's
    synthesized directly by suite_cap.py's _synthesize_dynamic_loop_count_args
    from the suite XML's own subcycle structure, exactly var_compat's
    num_subcycles_for_effr shape), so the scheme-table scan in
    _build_suite_variables_fn has nothing to find on its own."""

    _SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <subcycle loop="dynamic_loop_count">
      <scheme>scheme_a</scheme>
    </subcycle>
  </group>
</suite>
"""

    _SCHEME_META = f"""\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
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

    _HOST_META = """\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
[ x_host ]
  standard_name = matched_scalar
  units = m
  type = real
  kind = kind_phys
  dimensions = ()
[ num_loops ]
  standard_name = dynamic_loop_count
  units = count
  type = integer
  dimensions = ()
"""

    def test_dynamic_loop_count_std_name_included(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context, [self._SCHEME_META], [self._HOST_META],
            suite_xml=self._SUITE_XML,
        )
        body = _suite_variables_body(fortran)
        assert "dynamic_loop_count" in body, (
            f"synthesized subcycle loop-count std_name missing from suite_variables:\n{body}"
        )


class TestActiveExpressionReferenceIncluded:
    """A host DDT member declares `active = (some_conditional_flag)`, and
    some_conditional_flag is never itself a scheme argument anywhere --
    exactly var_compat's flag_indicating_cloud_microphysics_has_ice shape,
    referenced only inside test_host_data.meta's own `active =` expressions
    on effri/nci, never declared as a scheme arg standard_name.

    This module has exactly one suite, matching this fix's own scoping
    restriction (see ccpp_cap.py's Pass 2c comment) -- a second, multi-suite
    regression is covered by the existing capgen-xml.mlir FileCheck goldens
    instead of duplicated here."""

    _SCHEME_META = f"""\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
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

    _HOST_META = """\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
[ x_host ]
  standard_name = matched_scalar
  units = m
  type = real
  kind = kind_phys
  dimensions = ()
[ y_host ]
  standard_name = conditionally_present_value
  units = m
  type = real
  kind = kind_phys
  dimensions = ()
  active = (some_conditional_flag)
"""

    def test_active_expression_std_name_included(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context, [self._SCHEME_META], [self._HOST_META]
        )
        body = _suite_variables_body(fortran)
        assert "some_conditional_flag" in body, (
            f"active= expression's referenced std_name missing from suite_variables:\n{body}"
        )
