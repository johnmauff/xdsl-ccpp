"""`active` conditions become typed i1 expression ops (active-condition-ir):
each standard name is a reference to its host variable, operators are
`arith` ops, and the Fortran printer spells the result."""

from io import StringIO

import pytest
from xdsl.dialects import llvm

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.backend.print_ftn import ftnPrintContext
from xdsl_ccpp.transforms.suitecap.active import _resolve_active_condition
from xdsl_ccpp.transforms.util.ccpp_descriptors import BuildMetaDataDescriptions
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module

pytestmark = pytest.mark.usefixtures("legacy_mode")

_SCHEME_META = f"""\
[ccpp-table-properties]
  name = act_scheme
  type = scheme
[ccpp-arg-table]
  name = act_scheme_run
  type = scheme
{CCPP_MANDATORY_ARGS}
"""


def _host_var(local, std, ftn_type):
    return f"""\
[ {local} ]
  standard_name = {std}
  units = 1
  type = {ftn_type}
  dimensions = ()
"""


_HOST_META = f"""\
[ccpp-table-properties]
  name = act_host_mod
  type = module
[ccpp-arg-table]
  name = act_host_mod
  type = module
{_host_var("flag_a", "test_flag_a", "logical")}
{_host_var("flag_b", "test_flag_b", "logical")}
{_host_var("n", "test_count", "integer")}
{_host_var("x", "test_real", "real | kind = kind_phys")}
{_host_var("label", "test_label", "character | kind = len=8")}
"""


@pytest.fixture
def meta_data(run_host_match):
    module = run_host_match(
        scheme_metas=[_SCHEME_META], host_metas=[_HOST_META],
        suite_xml=minimal_suite_xml("act_scheme", suite_name="act_suite"),
    )
    bmdd = BuildMetaDataDescriptions()
    bmdd.traverse(find_ccpp_module(module.body.block.ops))
    return bmdd.meta_data


def _condition(meta_data, text, stubs=None):
    op = _resolve_active_condition(meta_data, text, [] if stubs is None else stubs)
    ctx = ftnPrintContext(output=StringIO())
    ctx.register_binops()
    return ctx._render_expr(op)


@pytest.mark.parametrize("text, fortran", [
    ("test_flag_a", "flag_a"),
    ("(test_flag_a)", "flag_a"),
    ("(test_count > 0)", "n .gt. 0"),
    ("test_count .le. 3 .and. test_flag_a", "n .le. 3 .and. flag_a"),
    ("test_flag_a .and. .not. test_flag_b", "flag_a .and. (.NOT. (flag_b))"),
    ("test_flag_a .eqv. .true.", "flag_a"),
    ("test_flag_a .eqv. .false.", ".NOT. (flag_a)"),
    ("test_flag_a .neqv. test_flag_b", "flag_a .neqv. flag_b"),
    ("test_flag_a .eqv. test_flag_b", ".NOT. (flag_a .neqv. flag_b)"),
    ("test_real >= 0", "x >= 0.0"),
])
def test_conditions_print(meta_data, text, fortran):
    assert _condition(meta_data, text) == fortran


def test_use_stubs_once_per_variable(meta_data):
    stubs = []
    _condition(meta_data, "test_flag_a .or. (test_flag_a .and. test_count > 1)", stubs)
    names = [s.sym_name.data for s in stubs if isinstance(s, llvm.GlobalOp)]
    assert names == ["flag_a", "n"]


@pytest.mark.parametrize("text, message", [
    ("no_such_variable", "not a host or module variable"),
    ("test_flag_a > 0", "cannot compare a logical"),
    ("test_count .and. test_flag_a", "not logical"),
    ("test_label", "only logical, integer and real"),
])
def test_invalid_conditions(meta_data, text, message):
    with pytest.raises(ValueError, match=message):
        _condition(meta_data, text)
