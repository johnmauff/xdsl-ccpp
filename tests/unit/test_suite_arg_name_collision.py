"""Unit tests for suite_cap.py's dummy-argument-name collision handling.

Different schemes are developed independently and routinely pick the same
generic local Fortran arg name (e.g. ``scalar_var``) for entirely unrelated
standard_names -- CCPP's own data model treats a scheme's local name as
private, decoupled from identity by standard_name, so this is expected, not
a metadata-authoring mistake. Found via a Copilot review comment on
examples/var_compat's real generated Fortran (PR #41): four schemes there
all use the bare name ``scalar_var`` for four different standard_names, and
the suite's combined subroutine signature ended up with ``scalar_var``
repeated three times over -- invalid, duplicate-dummy-argument Fortran.

Two things had to be fixed together in suite_cap.py's _build_block_signature:
  - The dummy-argument *name* printed in the signature: now prefers the
    host-matched canonical name (model_var_name) over the scheme's own local
    name, but only for entries that actually collide -- every non-colliding
    arg keeps its original name, unchanged.
  - The *data wiring*: data_ops (keyed by the scheme's own bare arg name) is
    unable to distinguish the colliding entries either, so without also
    registering each entry under a ("std_name", ...) tagged key (already an
    established pattern here, used elsewhere for SuiteOwned framework vars),
    every scheme sharing the same bare name would silently be called with
    whichever entry was processed last, regardless of which standard_name it
    actually declared -- a silent wrong-value bug, not just a naming
    cosmetic. Confirmed and fixed by tracing this exact failure mode with
    examples/var_compat's real generated code before landing the final fix.

A Copilot review comment on the PR carrying this fix (#42) pointed out that
the original test's own duplicate check could miss a collision between args
of different shape (scalar vs array) or intent, since it compared raw
declaration text instead of just the dummy-argument name. Investigating
that led to a real gap in the *production* code, not just the test:
suite_cap.py's collision detection compared the internal, possibly-suffixed
name_hint (e.g. "x" vs "x__in" for a scalar vs. an intent(in) array), but
print_ftn.py strips that suffix before printing -- so both would print as
the identical duplicate name "x" while going undetected as a collision.
Fixed by comparing the *printed* name (suffix stripped) everywhere
suite_cap.py does collision bookkeeping; see
TestCollisionAcrossShapeAndIntent for direct regression coverage.
"""

from io import StringIO

import pytest

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP
from xdsl_ccpp.transforms.suite_meta import MetaCAP

_TWO_SCHEME_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <scheme>scheme_a</scheme>
    <scheme>scheme_b</scheme>
  </group>
</suite>
"""


def _scheme_meta(name: str, std_name: str) -> str:
    return f"""\
[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_run
  type = scheme
[ x ]
  standard_name = {std_name}
  units = 1
  type = real
  kind = kind_phys
  dimensions = ()
  intent = in
{CCPP_MANDATORY_ARGS}
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
    """Extract just the dummy-argument name from a Fortran declaration line,
    stripping any array-shape suffix (e.g. "x(:, :)" -> "x") so a scalar and
    an array sharing the same name are correctly seen as the same
    (duplicate) declared identifier -- a real collision, as flagged by a
    Copilot review comment on PR #42 pointing out the original version of
    this check compared the raw, un-stripped declaration text instead."""
    return line.strip().split("::")[1].strip().split("(")[0].strip()


class TestCollisionResolvedViaHostName:
    """Both schemes' own arg is named "x", for two different standard_names
    -- but the host gives each standard_name a distinct local name, so the
    collision is fully resolvable."""

    _HOST_META = """\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
[ host_x_a ]
  standard_name = std_a
  units = 1
  type = real
  kind = kind_phys
  dimensions = ()
[ host_x_b ]
  standard_name = std_b
  units = 1
  type = real
  kind = kind_phys
  dimensions = ()
"""

    def test_signature_has_no_duplicate_dummy_arg_names(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_scheme_meta("scheme_a", "std_a"), _scheme_meta("scheme_b", "std_b")],
            [self._HOST_META],
        )
        fn = _fn_body(fortran, "test_suite_suite_physics")
        # Full signature line may wrap; just check the two host names both
        # appear as declared dummy args and never collide on "x".
        assert "host_x_a" in fortran
        assert "host_x_b" in fortran
        declared = [
            _declared_arg_name(line)
            for line in fn.splitlines()
            if "intent(" in line and "::" in line
        ]
        assert len(declared) == len(set(declared)), (
            f"duplicate dummy-argument declaration(s): {declared}"
        )

    def test_each_scheme_call_gets_its_own_correct_value(self, run_host_match, ccpp_context):
        """The real bug this fix closes: without also fixing the data wiring
        (not just the printed name), both scheme calls would silently
        receive whichever entry was resolved last, regardless of which
        standard_name each scheme actually declared."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_scheme_meta("scheme_a", "std_a"), _scheme_meta("scheme_b", "std_b")],
            [self._HOST_META],
        )
        fn = _fn_body(fortran, "test_suite_suite_physics")
        call_a = next(line for line in fn.splitlines() if "call scheme_a_run" in line)
        call_b = next(line for line in fn.splitlines() if "call scheme_b_run" in line)
        assert "host_x_a" in call_a
        assert "host_x_b" not in call_a
        assert "host_x_b" in call_b
        assert "host_x_a" not in call_b


class TestCollisionAcrossShapeAndIntent:
    """Both schemes' own arg is named "x" for two different standard_names,
    but one is a scalar intent(in) arg (no name_hint suffix) and the other is
    an array intent(in) arg (gets an internal "__in" name_hint suffix, which
    print_ftn.py strips before emitting the Fortran identifier). Collision
    detection must compare on the *printed* name, not the raw, suffixed
    name_hint -- otherwise "x" and "x__in" look like different names and the
    collision goes undetected, even though both print as the literal
    duplicate dummy-argument name "x". Found via a Copilot review comment on
    PR #42 questioning whether the original collision test could miss a
    shape/intent-driven case like this one.
    """

    _HOST_META = """\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
[ host_x_a ]
  standard_name = std_a
  units = 1
  type = real
  kind = kind_phys
  dimensions = ()
[ host_x_b ]
  standard_name = std_b
  units = 1
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
"""

    _SCALAR_SCHEME = _scheme_meta("scheme_a", "std_a")

    _ARRAY_SCHEME = f"""\
[ccpp-table-properties]
  name = scheme_b
  type = scheme
[ccpp-arg-table]
  name = scheme_b_run
  type = scheme
[ x ]
  standard_name = std_b
  units = 1
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  intent = in
{CCPP_MANDATORY_ARGS}
"""

    def test_signature_has_no_duplicate_dummy_arg_names(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [self._SCALAR_SCHEME, self._ARRAY_SCHEME],
            [self._HOST_META],
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

    def test_each_scheme_call_gets_its_own_correct_value(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [self._SCALAR_SCHEME, self._ARRAY_SCHEME],
            [self._HOST_META],
        )
        fn = _fn_body(fortran, "test_suite_suite_physics")
        call_a = next(line for line in fn.splitlines() if "call scheme_a_run" in line)
        call_b = next(line for line in fn.splitlines() if "call scheme_b_run" in line)
        assert "host_x_a" in call_a
        assert "host_x_b" not in call_a
        assert "host_x_b" in call_b
        assert "host_x_a" not in call_b


class TestCollisionWithoutHostNameRaises:
    """Neither scheme's colliding arg has a host match (no model_var_name
    available to disambiguate with) -- must fail loudly at generation time
    rather than silently emit invalid, duplicate-dummy-argument Fortran.

    Deliberately skips HostVariableMatchPass (unlike the class above) so
    neither arg gets model_var_name set, without hitting its separate
    "no matching host model variable" hard failure -- ArgOwnershipPass
    classifies an arg with no host metadata at all as a plain, unresolved
    block arg on its own, which is exactly the "no host name available"
    case this fix must still catch.
    """

    def test_raises_clear_error(self, build_module, ccpp_context):
        module = build_module(
            [_scheme_meta("scheme_a", "std_a"), _scheme_meta("scheme_b", "std_b")],
            [],
            _TWO_SCHEME_SUITE_XML,
        )
        MetaCAP().apply(ccpp_context, module)
        ArgOwnershipPass().apply(ccpp_context, module)
        with pytest.raises(ValueError, match="dummy-argument name collision"):
            SuiteCAP().apply(ccpp_context, module)
