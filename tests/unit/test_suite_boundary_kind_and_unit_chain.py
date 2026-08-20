"""Unit tests for suite_cap.py's non-divergent kind+unit cast chaining.

A single arg can carry BOTH a kind mismatch and a unit mismatch against
the host at once (e.g. host declares kind_phys/meters, scheme declares
kind=8/centimeters) -- this is the ordinary, non-divergent case (every
scheme sharing the standard_name agrees with every other scheme; only
the host's own declaration differs), so it goes through
_build_block_signature's suite-boundary conversion rather than the
per-call-site divergent marshaling covered by
test_suite_cross_scheme_unit_kind.py.

Before this fix, _apply_kind_casts and _apply_unit_conversions each
independently read from and wrote back to the raw original block arg,
instead of chaining (the unit conversion should read the kind cast's own
result when both apply, and the write-backs must undo the chain in
reverse -- unit first, then kind). Caught by Copilot review (PR #82):
the kind write-back's result was silently discarded by the following
unit write-back, since both targeted the same original block arg and
only the last-executed statement's effect survived -- correct only by
coincidence of _assemble_func's op-emission order and Fortran's
automatic real-kind promotion in expressions, not because the marshaling
was actually correct. This module pins the real, chained-correctly
Fortran output so a future regression is actually caught rather than
relying on the accident again.
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
  kind = 8
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


class TestNonDivergentKindAndUnitChain:
    """scheme_a is the only scheme declaring shared_var, in kind=8/cm,
    against the host's kind_phys/meters -- a single arg with BOTH
    mismatches at once, not a cross-scheme divergence."""

    def test_forward_chain_reads_kind_cast_result(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context)
        fn = _fn_body(fortran, "test_suite_suite_physics")
        kind_cast_line = next(l for l in fn.splitlines() if "x_kind_cast = " in l)
        unit_conv_line = next(l for l in fn.splitlines() if "x_unit_conv = " in l)
        assert "real(x, kind=8)" in kind_cast_line
        # The unit conversion must read the kind cast's own result
        # (x_kind_cast), not the raw host arg (x) directly.
        assert "x_kind_cast * 100.0_8" in unit_conv_line

    def test_call_uses_the_fully_converted_value(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context)
        fn = _fn_body(fortran, "test_suite_suite_physics")
        call_line = next(l for l in fn.splitlines() if "call scheme_a_run" in l)
        assert "x=x_unit_conv" in call_line.replace(" ", "")

    def test_writeback_undoes_unit_before_kind(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context)
        fn = _fn_body(fortran, "test_suite_suite_physics")
        lines = fn.splitlines()
        call_idx = next(i for i, l in enumerate(lines) if "call scheme_a_run" in l)
        writeback_lines = [l for l in lines[call_idx + 1:] if "x_kind_cast" in l or l.strip().startswith("x =")]
        # Unit write-back (into x_kind_cast) must execute before the kind
        # write-back (into x) reads that same x_kind_cast.
        unit_wb_idx = next(i for i, l in enumerate(writeback_lines) if "x_kind_cast = " in l)
        kind_wb_idx = next(i for i, l in enumerate(writeback_lines) if l.strip().startswith("x ="))
        assert unit_wb_idx < kind_wb_idx
        assert "x_unit_conv * 0.01_8" in writeback_lines[unit_wb_idx]
        assert "real(x_kind_cast, kind=kind_phys)" in writeback_lines[kind_wb_idx]
