"""Regression test for task70-arraysection: consolidating ArraySectionOp
into RankReducingSliceOp's own all-'R' (empty scalar_indices) case.

ArraySectionOp's result type was always hard-pinned to its source operand's
own type, regardless of how many (lower, upper) pairs it was given.
RankReducingSliceOp instead computes its result rank from dim_pattern.count
("R") -- correct for its original, only prior use (CCPP variable promotion),
but wrong whenever a source's own declared rank doesn't match the pattern's
'R' count. A real instance of that mismatch (a DDT member ref whose own
member_name already carries a baked-in fixed-index subscript, interacting
with print_ftn.py's existing-subscript merge logic to silently discard an
over-resolved extra dimension) was found via a real
xdsl.utils.exceptions.VerifyException ("operand type mismatch ...") while
migrating examples/advection's own generated IR during this consolidation
-- that specific case is NOT reproduced here (its exact host-matching setup
is involved enough that examples/advection's own existing
tests/filecheck/examples/{completed_ir,end_to_end}/advection-xml.mlir
goldens are the real regression guard for it, empirically confirmed to
fail with the bug present and pass once fixed).

This test instead covers the common, simple case explicitly -- a plain 2D
host array sliced by column+vertical chunk, source rank == pattern's 'R'
count exactly (run_dispatch.py's _build_array_section_ops Host branch) --
previously exercised only incidentally through other tests' own assertions
on printed Fortran text, never through an explicit module.verify() call.
Fixed by having RankReducingSliceOp's all-'R' case copy its source's own
type verbatim, exactly like ArraySectionOp always did, rather than
recomputing rank from dim_pattern's length -- a no-op for this simple case
(rank already matches either way) but the right general rule, matching
ArraySectionOp's own semantics exactly for every all-'R' case, not just
the ones this particular test happens to cover.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

_HOST_META = """\
[ccpp-table-properties]
  name = test_host
  type = host
[ccpp-arg-table]
  name = test_host
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
"""

_HOST_MOD_META = """\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
[ ncols ]
  standard_name = horizontal_dimension
  units = count
  type = integer
  dimensions = ()
[ pver ]
  standard_name = vertical_layer_dimension
  units = count
  type = integer
  dimensions = ()
[ y_host ]
  standard_name = some_2d_array_var
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
"""

_SCHEME_META = f"""\
[ccpp-table-properties]
  name = slice_scheme
  type = scheme
[ccpp-arg-table]
  name = slice_scheme_run
  type = scheme
[ y ]
  standard_name = some_2d_array_var
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""


def _build_module(run_host_match, ccpp_context):
    module = run_host_match(
        scheme_metas=[_SCHEME_META],
        host_metas=[_HOST_META, _HOST_MOD_META],
        suite_xml=minimal_suite_xml("slice_scheme"),
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    return module


class TestRankReducingSliceAllRCaseVerifies:
    def test_module_verifies_cleanly(self, run_host_match, ccpp_context):
        """The all-'R' RankReducingSliceOp built for y_host's column+vertical
        slice must produce a result type consistent with what it's actually
        passed to -- module.verify() raising here is exactly the failure
        mode this consolidation introduced and then fixed."""
        module = _build_module(run_host_match, ccpp_context)
        module.verify()

    def test_slice_printed_correctly(self, run_host_match, ccpp_context):
        module = _build_module(run_host_match, ccpp_context)
        out = StringIO()
        print_to_ftn(module, out)
        fortran = out.getvalue()
        fn_body = fortran.split("subroutine ccpp_physics_run")[1].split(
            "end subroutine ccpp_physics_run"
        )[0]
        call_line = next(
            line for line in fn_body.splitlines() if "call test_suite_physics" in line
        )
        assert "y_host(col_start:col_end, 1:pver)" in call_line, call_line
