"""Unit tests for print_ftn.py's forward-conversion op printing (CCPPKindCastOp/
CCPPUnitConvertOp/CCPPVerticalFlipOp/CCPPRowMajorConvertOp) -- a real gfortran
runtime crash found only by actually running examples/var_compat (ifx and
every existing FileCheck golden silently accepted the missing deallocate):

    At line 184 of file examples/var_compat/var_compatibility_suite_cap.F90
    Fortran runtime error: Attempting to allocate already allocated variable
    'effrr_in_unit_conv'

Root cause: each "forward" conversion op (allocate a local temp, convert into
it) is paired with a "write-back" op (write the temp back to the host,
deallocate it) -- but the deallocate only ever happens inside the WriteBackOp
case. A value that's pure intent(in) (var_compat's effrr_in, consumed by
effr_calc_run) never has a write-back at all -- there's nothing to write
back -- so its conversion temp is never deallocated, full stop, regardless
of intent. That's invisible for a subroutine called only once (Fortran
deallocates non-SAVE locals automatically on return), but
var_compatibility_suite_suite_radiation's own call to effr_calc_run sits
inside a nested `do ccpp_loop_cnt0 = 1, 2 / do ccpp_loop_cnt = 1, 2` subcycle
loop -- the SAME temp gets allocated a second time, within the same
subroutine invocation, before Fortran ever gets a chance to deallocate it.

Fixed by printing a guarded deallocate (`if (allocated(x)) deallocate(x)`,
the same pattern CCPPSafeDeallocOp already uses elsewhere in this file)
immediately before every "allocate(...)" statement these four op cases
print -- independent of whether a write-back exists, so it's safe for pure
intent(in) values, and idempotent (a no-op on first entry, since the
variable starts deallocated) so it doesn't change behavior for the ordinary,
non-looped case either.

Covers three of the four affected op cases (CCPPKindCastOp, CCPPUnitConvertOp,
CCPPVerticalFlipOp) via full-pipeline SuiteCAP() output; CCPPRowMajorConvertOp
got the identical one-line fix but isn't separately fixtured here (same code
shape in the same printer function, lower marginal risk, and no existing
example exercises it in combination with looping the way effrr_in's real bug
did).
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP


def _fortran_output(run_host_match, ccpp_context, scheme_meta, host_meta) -> str:
    module = run_host_match(
        scheme_metas=[scheme_meta], host_metas=[host_meta],
        suite_xml=minimal_suite_xml("scheme_a"),
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _assert_guarded(fortran: str, var_name: str):
    """Every 'allocate(var_name(...))' line must be immediately preceded by
    'if (allocated(var_name)) deallocate(var_name)'."""
    lines = [line.strip() for line in fortran.splitlines()]
    alloc_lines = [i for i, line in enumerate(lines) if line.startswith(f"allocate({var_name}(")]
    assert alloc_lines, f"expected an allocate({var_name}(...)) line, found none:\n{fortran}"
    for i in alloc_lines:
        assert i > 0, f"allocate({var_name}...) is the first line, no room for a guard"
        guard = lines[i - 1]
        assert guard == f"if (allocated({var_name})) deallocate({var_name})", (
            f"allocate({var_name}...) at line {i} not preceded by a guarded deallocate, "
            f"got {guard!r} instead:\n{fortran}"
        )


class TestKindCastGuardedDeallocate:
    """scheme_a's array arg declares a different kind than the host
    (mirroring helloworld's temp_level, kind_dyn vs kind_phys) -- an
    intent=in array, so CCPPKindCastOp's own allocate is the only one ever
    printed for it (no write-back, hence no deallocate without this fix)."""

    _SCHEME_META = f"""\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
[ccpp-arg-table]
  name = scheme_a_run
  type = scheme
[ x ]
  standard_name = shared_var
  units = m
  type = real
  kind = kind_dyn
  dimensions = (horizontal_dimension, vertical_layer_dimension)
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
[ host_x ]
  standard_name = shared_var
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
"""

    def test_kind_cast_temp_guarded(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context, self._SCHEME_META, self._HOST_META)
        _assert_guarded(fortran, "x_kind_cast")


class TestUnitConvertGuardedDeallocate:
    """scheme_a's array arg declares different units than the host -- also
    intent=in, so only CCPPUnitConvertOp's forward allocate is ever printed
    for it."""

    _SCHEME_META = f"""\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
[ccpp-arg-table]
  name = scheme_a_run
  type = scheme
[ x ]
  standard_name = shared_var
  units = km
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
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
[ host_x ]
  standard_name = shared_var
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
"""

    def test_unit_convert_temp_guarded(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context, self._SCHEME_META, self._HOST_META)
        _assert_guarded(fortran, "x_unit_conv")


class TestVerticalFlipGuardedDeallocate:
    """Two schemes share a standard_name; scheme_b declares top_at_one=True
    while scheme_a doesn't (var_compat's own effr_calc/effr_diag vs.
    effr_pre/effr_post/effrs_calc shape -- no host ever declares an explicit
    vertical convention to compare against, so the non-declaring schemes
    define the shared, unflipped representation). scheme_b's own arg is
    intent=in, so only CCPPVerticalFlipOp's forward allocate is ever printed
    for it."""

    _SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <scheme>scheme_a</scheme>
    <scheme>scheme_b</scheme>
  </group>
</suite>
"""

    _SCHEME_A_META = f"""\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
[ccpp-arg-table]
  name = scheme_a_run
  type = scheme
[ x ]
  standard_name = shared_var
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

    _SCHEME_B_META = f"""\
[ccpp-table-properties]
  name = scheme_b
  type = scheme
[ccpp-arg-table]
  name = scheme_b_run
  type = scheme
[ y ]
  standard_name = shared_var
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  intent = in
  top_at_one = True
{CCPP_MANDATORY_ARGS}
"""

    _HOST_META = """\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
[ host_x ]
  standard_name = shared_var
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
"""

    def test_vertical_flip_temp_guarded(self, run_host_match, ccpp_context):
        module = run_host_match(
            scheme_metas=[self._SCHEME_A_META, self._SCHEME_B_META],
            host_metas=[self._HOST_META],
            suite_xml=self._SUITE_XML,
        )
        ArgOwnershipPass().apply(ccpp_context, module)
        SuiteCAP().apply(ccpp_context, module)
        out = StringIO()
        print_to_ftn(module, out)
        fortran = out.getvalue()
        _assert_guarded(fortran, "y_vert_flip")
