"""lang-neutral-expr-ir Stage 3c: UnitConvertOp's structured conversion_op
path, driven through the real metadata pipeline (not just pure op
construction -- see test_expr_ir_dual_print.py's TestUnitConvertRegionShape
for that).

Only a scalar arg whose own declared kind is a bare numeric literal (e.g.
`kind = 8`) with no preceding kind-cast is eligible for the structured
`arith` form (see suite_cap.py's `_apply_kind_and_unit_casts`); every
other real kind (named, e.g. kind_phys) and every array-shaped arg keeps
the opaque-text `to_scheme_expr`/`to_host_expr` form permanently. This
module proves: the eligible case actually takes the structured path, its
printed Fortran is byte-identical to what the opaque-text path would have
produced for the same inputs, and both ineligible cases (named kind,
array shape) still take the opaque-text path.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl.dialects import arith
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.dialects.ccpp_utils import UnitConvertOp
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

_ONE_SCHEME_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <scheme>scheme_a</scheme>
  </group>
</suite>
"""


def _scheme_meta(kind: str, dimensions: str, units: str = "cm") -> str:
    return f"""\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
[ccpp-arg-table]
  name = scheme_a_run
  type = scheme
[ x ]
  standard_name = shared_var
  units = {units}
  type = real
  kind = {kind}
  dimensions = {dimensions}
  intent = inout
{CCPP_MANDATORY_ARGS}
"""


def _host_meta(kind: str, dimensions: str, units: str = "m") -> str:
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
  dimensions = {dimensions}
"""


def _run(
    run_host_match, ccpp_context, scheme_kind: str, host_kind: str, dimensions: str,
    scheme_units: str = "cm", host_units: str = "m",
):
    module = run_host_match(
        scheme_metas=[_scheme_meta(scheme_kind, dimensions, scheme_units)],
        host_metas=[_host_meta(host_kind, dimensions, host_units)],
        suite_xml=_ONE_SCHEME_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    (unit_convert_op,) = [op for op in module.walk() if isinstance(op, UnitConvertOp)]
    out = StringIO()
    print_to_ftn(module, out)
    return unit_convert_op, out.getvalue()


def _fn_body(fortran: str, fn_name: str) -> str:
    return fortran.split(f"subroutine {fn_name}")[1].split(f"end subroutine {fn_name}")[0]


class TestScalarBareDigitKindTakesStructuredPath:
    """scheme_a's own kind (8) matches the host's (8, both bare digits) --
    no kind mismatch at all, only a unit mismatch (cm vs m) -- so `cur` is
    a plain block argument and the structured path's gate is fully met."""

    def test_builds_a_conversion_region_not_opaque_text(self, run_host_match, ccpp_context):
        unit_convert_op, _fortran = _run(
            run_host_match, ccpp_context, scheme_kind="8", host_kind="8", dimensions="()",
        )
        assert unit_convert_op.to_scheme_expr is None
        assert unit_convert_op.conversion is not None
        root = unit_convert_op.conversion.block.last_op
        assert isinstance(root, arith.MulfOp)
        assert isinstance(root.rhs.owner, arith.ConstantOp)
        assert root.rhs.owner.value.value.data == 100.0

    def test_printed_fortran_matches_opaque_path_text_exactly(self, run_host_match, ccpp_context):
        # UNIT_CONVERSIONS[("cm", "m")] == ("* 100.0", "* 0.01") -- the
        # opaque-text path would print this exact suffixed literal
        # ("* 100.0_8") for a kind=8 arg; the structured path must print
        # byte-identically, since both paths must agree on output text.
        _unit_convert_op, fortran = _run(
            run_host_match, ccpp_context, scheme_kind="8", host_kind="8", dimensions="()",
        )
        fn = _fn_body(fortran, "test_suite_physics")
        unit_conv_line = next(l for l in fn.splitlines() if "x_unit_conv = " in l)
        assert "x * 100.0_8" in unit_conv_line


class TestNamedKindStaysOnOpaquePath:
    """kind_phys is a named kind -- real_kind_width returns None, so even
    with the identical unit mismatch, the structured path's gate is not
    met and the opaque-text form is used, exactly as before this change."""

    def test_builds_opaque_text_not_a_conversion_region(self, run_host_match, ccpp_context):
        unit_convert_op, _fortran = _run(
            run_host_match, ccpp_context,
            scheme_kind="kind_phys", host_kind="kind_phys", dimensions="()",
        )
        assert unit_convert_op.to_scheme_expr is not None
        assert unit_convert_op.conversion is None


class TestExponentFormLiteralStaysOnOpaquePath:
    """(um, m) uses exponent-form literals ("* 1.0E6" / "* 1.0E-6") whose
    spelling Python's float-to-str round trip can't reproduce exactly
    ("1.0E6" -> "1000000.0", "1.0E-6" -> "1e-06") -- _parse_unit_conversion
    must recognize this and stay on the opaque-text path rather than
    silently emitting a differently-spelled (if numerically equal)
    literal (Copilot PR #115 review)."""

    def test_builds_opaque_text_not_a_conversion_region(self, run_host_match, ccpp_context):
        unit_convert_op, _fortran = _run(
            run_host_match, ccpp_context, scheme_kind="8", host_kind="8", dimensions="()",
            scheme_units="um", host_units="m",
        )
        assert unit_convert_op.to_scheme_expr is not None
        assert unit_convert_op.conversion is None

    def test_printed_fortran_keeps_the_original_literal_spelling(self, run_host_match, ccpp_context):
        _unit_convert_op, fortran = _run(
            run_host_match, ccpp_context, scheme_kind="8", host_kind="8", dimensions="()",
            scheme_units="um", host_units="m",
        )
        fn = _fn_body(fortran, "test_suite_physics")
        unit_conv_line = next(l for l in fn.splitlines() if "x_unit_conv = " in l)
        assert "x * 1.0E6_8" in unit_conv_line


class TestArrayShapedArgStaysOnOpaquePath:
    """A bare-digit kind on an array-shaped arg is still ineligible -- one
    arith op cannot represent an array-wide "+ 273.15"-style assignment."""

    def test_builds_opaque_text_not_a_conversion_region(self, run_host_match, ccpp_context):
        unit_convert_op, _fortran = _run(
            run_host_match, ccpp_context, scheme_kind="8", host_kind="8",
            dimensions="(horizontal_dimension)",
        )
        assert unit_convert_op.to_scheme_expr is not None
        assert unit_convert_op.conversion is None
