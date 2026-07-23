"""Regression test: a scalar intent(inout) argument with a real kind or unit
mismatch against the host must still be declared intent(inout) in the
generated suite subroutine, not intent(in).

Found via a Copilot review comment on the PR carrying the cross-scheme
unit/kind marshaling fix (examples/var_compat). suite_cap.py's
_build_block_signature's kind_cast_ops/unit_convert_ops loops reassign
data_ops[fn_arg.name] to the suite-boundary conversion temp's SSA value (so
generateSchemeSubroutineCallOps and later reassignments see the converted
value) -- correct for that purpose. But _assemble_func's inout_return_vals
used to read straight from data_ops[a.name] too, meaning it picked up the
SAME conversion temp instead of the original block arg. print_ftn.py decides
whether a scalar dummy argument is intent(inout) by checking whether it
appears in the generated func.ReturnOp's value list (see its docstring) --
so with the conversion temp standing in for the original block arg there,
the original arg silently dropped out of that list and got declared
intent(in), even though the write-back that follows still assigns into it.
Declaring an argument intent(in) and then assigning to it is invalid
Fortran and would not compile.

Fixed by building inout_return_vals from new_block.args[idx] directly (the
original block arg, indexed by position), rather than from data_ops[a.name]
(which may have been reassigned for reasons unrelated to what the return
list needs to represent: the original argument's identity, for the
printer's intent-detection).

This is a different code path from the cross-scheme divergent marshaling
fix (see test_suite_cross_scheme_unit_kind.py) -- it affects the ordinary,
single-scheme suite-boundary conversion, not the per-call marshaling for
standard_names multiple schemes declare differently from each other. Only
became reachable in practice once examples/var_compat's own unit_conversions
table gained real entries for the pairs it needs (before that, these
specific mismatches only ever warned and passed through unconverted).
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.backend.print_ftn import print_to_ftn
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

_SCHEME_META = f"""\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
[ccpp-arg-table]
  name = scheme_a_run
  type = scheme
[ x ]
  standard_name = shared_var
  units = cm
  type = real
  kind = kind_phys
  dimensions = ()
  intent = inout
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
  dimensions = ()
"""


def _fortran_output(run_host_match, ccpp_context) -> str:
    module = run_host_match(
        scheme_metas=[_SCHEME_META], host_metas=[_HOST_META], suite_xml=_ONE_SCHEME_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fn_body(fortran: str, fn_name: str) -> str:
    return fortran.split(f"subroutine {fn_name}")[1].split(f"end subroutine {fn_name}")[0]


class TestScalarInoutWithUnitMismatchStaysInout:
    def test_declared_intent_is_inout(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context)
        fn = _fn_body(fortran, "test_suite_suite_physics")
        decl = next(line for line in fn.splitlines() if "intent(" in line and ":: x" in line)
        assert "intent(inout)" in decl, f"expected intent(inout), got: {decl!r}"

    def test_write_back_assignment_present(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context)
        fn = _fn_body(fortran, "test_suite_suite_physics")
        assert any(
            line.strip().startswith("x = ") for line in fn.splitlines()
        ), "expected a write-back assignment into x"
