"""A unit conversion at the suite boundary is data on UnitConvertOp -- an
operation ("add", "sub", "mul") and a factor -- driven through the real
metadata pipeline, for every argument shape: a scalar with a bare-digit
kind, a named kind, an exponent-form factor, and an array. The printed
Fortran gives the factor the argument's kind, keeping the factor's
spelling (1.0E6 stays 1.0E6).
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS
import pytest
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


@pytest.mark.parametrize("kind, dimensions, scheme_units, factor, printed", [
    ("8", "()", "cm", "100.0", "x * 100.0_8"),
    ("kind_phys", "()", "cm", "100.0", "x * 100.0_kind_phys"),
    ("8", "()", "um", "1.0E6", "x * 1.0E6_8"),
    ("8", "(horizontal_dimension)", "cm", "100.0", "x * 100.0_8"),
])
def test_conversion_is_operation_and_factor(
    run_host_match, ccpp_context, kind, dimensions, scheme_units, factor, printed,
):
    unit_convert_op, fortran = _run(
        run_host_match, ccpp_context, scheme_kind=kind, host_kind=kind,
        dimensions=dimensions, scheme_units=scheme_units,
    )
    assert unit_convert_op.operation.data == "mul"
    assert unit_convert_op.factor.data == factor
    fn = _fn_body(fortran, "test_suite_physics")
    unit_conv_line = next(l for l in fn.splitlines() if "x_unit_conv = " in l)
    assert printed in unit_conv_line
