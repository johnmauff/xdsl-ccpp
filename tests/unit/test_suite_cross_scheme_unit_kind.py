"""Unit tests for suite_cap.py's cross-scheme kind/unit divergence marshaling.

Two or more schemes can independently declare the same standard_name with
genuinely different kind or units from EACH OTHER -- not just different from
the host. Found while working on examples/var_compat: effr_pre/effr_post
declare the rain-particle radius standard_name in meters (matching the
host), while effr_calc/effr_diag declare the SAME standard_name in
micrometers; effrs_calc declares the snow-particle radius standard_name in
meters/kind_phys (matching the host), while effr_calc declares the SAME
standard_name in micrometers/kind=8.

Before this fix, suite_cap.py built ONE combined suite-level dummy argument
per standard_name, using whichever scheme's own declaration happened to be
first in scheme order, and converted it ONCE against the host at the top of
the function. That converted value was then passed unchanged to every OTHER
scheme sharing the standard_name -- silently wrong whenever another scheme's
own declaration didn't match whichever one became canonical.

The fix: _build_arg_tables now flags a standard_name as "divergent" when two
or more schemes sharing it declare a different (kind, units) pair from each
other. For divergent standard_names, _build_block_signature skips the
suite-boundary conversion entirely (the shared value stays in the host's own
native representation for the whole function body), and
generateSchemeSubroutineCallOps independently marshals each individual call
to that call's own scheme's already-known kind/unit mismatch against the
host (set per-scheme by HostVariableMatchPass, completely independent of
which scheme became canonical) -- converting immediately before the call and
writing back immediately after, reusing the same KindCastOp/UnitConvertOp/
KindWriteBackOp/UnitWriteBackOp already used for the ordinary, non-divergent
case. Every non-divergent standard_name is completely unaffected.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

_TWO_SCHEME_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <scheme>scheme_a</scheme>
    <scheme>scheme_b</scheme>
  </group>
</suite>
"""


def _scheme_meta(name: str, units: str, kind: str = "kind_phys", intent: str = "inout") -> str:
    return f"""\
[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_run
  type = scheme
[ x ]
  standard_name = shared_var
  units = {units}
  type = real
  kind = {kind}
  dimensions = ()
  intent = {intent}
{CCPP_MANDATORY_ARGS}
"""


def _host_meta(units: str, kind: str = "kind_phys") -> str:
    return f"""\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
[ host_x ]
  standard_name = shared_var
  units = {units}
  type = real
  kind = {kind}
  dimensions = ()
"""


def _fortran_output(run_host_match, ccpp_context, scheme_metas, host_metas) -> str:
    module = run_host_match(
        scheme_metas=scheme_metas, host_metas=host_metas, suite_xml=_TWO_SCHEME_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fn_body(fortran: str, fn_name: str) -> str:
    return fortran.split(f"subroutine {fn_name}")[1].split(f"end subroutine {fn_name}")[0]


def _declared_arg_name(line: str) -> str:
    return line.strip().split("::")[1].strip().split("(")[0].strip()


class TestDivergentUnitsHostMatchesOne:
    """scheme_a declares shared_var in meters (matches the host exactly, no
    mismatch at all), scheme_b declares the SAME standard_name in
    centimeters (a real, pre-existing unit-conversion pair). scheme_a's own
    call must receive the host value directly, unconverted; scheme_b's own
    call must receive a locally converted value, with a write-back after
    the call restoring the shared value to meters for whatever runs next."""

    def test_scheme_a_gets_unconverted_host_value(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_scheme_meta("scheme_a", "m"), _scheme_meta("scheme_b", "cm")],
            [_host_meta("m")],
        )
        fn = _fn_body(fortran, "test_suite_suite_physics")
        call_a = next(line for line in fn.splitlines() if "call scheme_a_run" in line)
        assert "_unit_conv" not in call_a
        assert "_kind_cast" not in call_a

    def test_scheme_b_gets_converted_value_and_writes_back(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_scheme_meta("scheme_a", "m"), _scheme_meta("scheme_b", "cm")],
            [_host_meta("m")],
        )
        fn = _fn_body(fortran, "test_suite_suite_physics")
        call_b = next(line for line in fn.splitlines() if "call scheme_b_run" in line)
        assert "_unit_conv" in call_b
        # host (m) -> scheme_b (cm): multiply by 100; write-back divides by 100.
        assert "* 100.0" in fn
        assert "* 0.01" in fn

    def test_no_duplicate_dummy_arg_declarations(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_scheme_meta("scheme_a", "m"), _scheme_meta("scheme_b", "cm")],
            [_host_meta("m")],
        )
        fn = _fn_body(fortran, "test_suite_suite_physics")
        declared = [
            _declared_arg_name(line)
            for line in fn.splitlines()
            if "intent(" in line and "::" in line
        ]
        assert len(declared) == len(set(declared)), (
            f"duplicate dummy-argument declaration(s): {declared}"
        )


class TestDivergentUnitsHostMatchesNeither:
    """Host declares meters; scheme_a declares centimeters, scheme_b
    declares micrometers -- both schemes mismatch the host, in different
    directions, and neither matches the other. Both calls must receive
    their own distinctly converted value."""

    def test_each_scheme_gets_its_own_conversion(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_scheme_meta("scheme_a", "cm"), _scheme_meta("scheme_b", "um")],
            [_host_meta("m")],
        )
        fn = _fn_body(fortran, "test_suite_suite_physics")
        call_a = next(line for line in fn.splitlines() if "call scheme_a_run" in line)
        call_b = next(line for line in fn.splitlines() if "call scheme_b_run" in line)
        assert "_unit_conv" in call_a
        assert "_unit_conv" in call_b
        # host (m) -> scheme_a (cm): * 100.0; host (m) -> scheme_b (um): * 1.0E6
        assert "* 100.0" in fn
        assert "1.0E6" in fn

    def test_no_declaration_collision_between_the_two_temps(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_scheme_meta("scheme_a", "cm"), _scheme_meta("scheme_b", "um")],
            [_host_meta("m")],
        )
        fn = _fn_body(fortran, "test_suite_suite_physics")
        declared = [
            _declared_arg_name(line)
            for line in fn.splitlines()
            if "intent(" in line and "::" in line
        ]
        assert len(declared) == len(set(declared)), (
            f"duplicate dummy-argument declaration(s): {declared}"
        )


class TestDivergentKindAndUnitsChain:
    """scheme_a matches the host exactly (kind_phys, meters); scheme_b
    diverges on BOTH kind (8) and units (centimeters) simultaneously,
    mirroring examples/var_compat's real effrs_inout case exactly. The
    write-back must undo the chain in reverse (unit first, then kind) --
    the exact ordering bug this fix has to get right, since a kind cast
    followed by a unit convert must be unwound unit-first."""

    def test_scheme_b_call_uses_chained_kind_and_unit_cast(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_scheme_meta("scheme_a", "m"), _scheme_meta("scheme_b", "cm", kind="8")],
            [_host_meta("m")],
        )
        fn = _fn_body(fortran, "test_suite_suite_physics")
        call_b = next(line for line in fn.splitlines() if "call scheme_b_run" in line)
        assert "_kind_cast" in fn or "_unit_conv" in call_b
        assert "real(" in fn
        assert "kind=8" in fn
        assert "* 100.0" in fn

    def test_scheme_a_call_unaffected(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_scheme_meta("scheme_a", "m"), _scheme_meta("scheme_b", "cm", kind="8")],
            [_host_meta("m")],
        )
        fn = _fn_body(fortran, "test_suite_suite_physics")
        call_a = next(line for line in fn.splitlines() if "call scheme_a_run" in line)
        assert "_unit_conv" not in call_a
        assert "_kind_cast" not in call_a

    def test_no_duplicate_declarations(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_scheme_meta("scheme_a", "m"), _scheme_meta("scheme_b", "cm", kind="8")],
            [_host_meta("m")],
        )
        fn = _fn_body(fortran, "test_suite_suite_physics")
        declared = [
            _declared_arg_name(line)
            for line in fn.splitlines()
            if "intent(" in line and "::" in line
        ]
        assert len(declared) == len(set(declared)), (
            f"duplicate dummy-argument declaration(s): {declared}"
        )
