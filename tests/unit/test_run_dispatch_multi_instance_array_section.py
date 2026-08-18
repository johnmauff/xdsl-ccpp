"""Regression test for a real bug found while implementing Stage 4 of the
multi-instance array-of-DDT-instance feature (ccpp_cap_refactor_plan.md's
instances/instances_advection entry, real capgen-v1's own multi-instance
model): print_ftn.py's CCPPArraySectionOp handler silently dropped the
"%member" suffix entirely when the DDT instance itself was already
subscripted by an instance index.

Found by actually regenerating examples/instances: `data_array2` (a genuine
1-D horizontal_dimension-dimensioned DDT member that gets column-sliced by
the existing lb:ub ArraySectionOp fallback) printed as just
`instance_data(instance)` -- the member access silently vanished, an
arity/identity mismatch that would either fail to compile or (worse) bind
the wrong dummy argument. `data_array`/`data_array_opt` (the OTHER two
members, whose own declared subscript is a fixed species index, not
column-sliced) were unaffected, since they never go through the buggy
ArraySectionOp merge path at all -- this only reproduces with a genuinely
column-sliced DDT member.

Root cause: the merge logic located the "existing subscript to merge into"
via source_name.find("(") -- the FIRST '(' in the whole string. Once
HostVarRefOp could also prepend an index_expr subscript before the member
(`instance_data(instance)%data_array2`), that first '(' is the INSTANCE
index, not the member's own subscript -- the merge logic treated "instance"
as an existing placeholder token, discarded everything after its matching
')' (the real member access), and rebuilt just "instance_data(instance)".

Fixed by searching for the member's own subscript only after the last '%'.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

_HOST_META = """\
[ccpp-table-properties]
  name = data
  type = host
[ccpp-arg-table]
  name = data
  type = host
[ col_start ]
  standard_name = horizontal_loop_begin
  units = count
  type = integer
  dimensions = ()
[ col_end ]
  standard_name = horizontal_loop_end
  units = count
  type = integer
  dimensions = ()
[ instance ]
  standard_name = instance_number
  units = index
  type = integer
  dimensions = ()
[ instance_data ]
  standard_name = instance_data
  units = ddt
  type = instance_type
  dimensions = (number_of_instances)
"""

_DDT_META = """\
[ccpp-table-properties]
  name = instance_type
  type = ddt
[ccpp-arg-table]
  name = instance_type
  type = ddt
[ data_array2 ]
  standard_name = data_array2
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
"""

_SCHEME_META = f"""\
[ccpp-table-properties]
  name = unit_conv_scheme
  type = scheme
[ccpp-arg-table]
  name = unit_conv_scheme_run
  type = scheme
[ instance ]
  standard_name = instance_number
  units = index
  type = integer
  dimensions = ()
  intent = in
[ arr ]
  standard_name = data_array2
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""


def _fortran_output(run_host_match, ccpp_context) -> str:
    module = run_host_match(
        scheme_metas=[_SCHEME_META],
        host_metas=[_HOST_META, _DDT_META],
        suite_xml=minimal_suite_xml("unit_conv_scheme"),
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fn_body(fortran: str, fn_name: str) -> str:
    return fortran.split(f"subroutine {fn_name}")[1].split(f"end subroutine {fn_name}")[0]


def _unwrapped(fortran_fragment: str) -> str:
    """Collapse Fortran line-continuation ('&' + newline + indent) so a
    call spanning multiple printed lines can be matched as one string."""
    return " ".join(
        line.rstrip().rstrip("&").strip() for line in fortran_fragment.splitlines()
    )


class TestArraySectionMemberSurvivesInstanceIndex:
    def test_member_and_index_both_present_in_call(self, run_host_match, ccpp_context):
        """The column-sliced DDT member must print as
        instance_data(instance)%data_array2(<slice>) inside ccpp_physics_run's
        own call to the suite -- both the instance index AND the member
        name, not just the bare indexed instance."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        fn = _unwrapped(_fn_body(fortran, "ccpp_physics_run"))
        assert "instance_data(instance)%data_array2(col_start:col_end)" in fn, (
            f"expected instance_data(instance)%data_array2(...), got: {fn!r}"
        )

    def test_bare_indexed_instance_without_member_not_printed(
        self, run_host_match, ccpp_context
    ):
        """Regression guard: the specific buggy output -- instance_data(instance)
        with NO %member trailing it -- must never appear in ccpp_physics_run."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        fn = _unwrapped(_fn_body(fortran, "ccpp_physics_run"))
        assert "instance_data(instance)%" in fn
        assert "instance_data(instance), " not in fn
        assert not fn.rstrip().endswith("instance_data(instance)")
