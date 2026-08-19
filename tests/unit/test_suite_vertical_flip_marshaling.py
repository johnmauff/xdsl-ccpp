"""Unit tests for suite_cap.py's per-call vertical-flip marshaling.

Stage 3 of the vertical-flip work: two or more schemes can share a
standard_name while disagreeing on top_at_one (examples/var_compat:
effr_pre/effr_post/effrs_calc don't declare it, effr_calc/effr_diag declare
it True). Since a host never declares an explicit vertical convention to
compare against (confirmed during earlier research), the schemes that don't
declare top_at_one define the shared, "not flipped" representation, and any
scheme that DOES declare it needs a per-call flip -- reusing the exact same
divergent_std_keys detection and per-call insertion point (in
generateSchemeSubroutineCallOps) already built for the cross-scheme kind/unit
marshaling fix (see test_suite_cross_scheme_unit_kind.py).

Also covers the case where kind, units, AND top_at_one all diverge on the
same argument at once (examples/var_compat's real effrs_inout case) --
the chain must apply forward as kind, then units, then flip, and the
write-back must undo it in the opposite order.
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


def _scheme_meta(
    name: str, top_at_one: bool = False, units: str = "m", kind: str = "kind_phys",
    optional: bool = False,
) -> str:
    top_at_one_line = "  top_at_one = True\n" if top_at_one else ""
    optional_line = "  optional = True\n" if optional else ""
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
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  intent = inout
{top_at_one_line}{optional_line}{CCPP_MANDATORY_ARGS}
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


def _fortran_output(run_host_match, ccpp_context, scheme_metas) -> str:
    module = run_host_match(
        scheme_metas=scheme_metas, host_metas=[_HOST_META], suite_xml=_TWO_SCHEME_SUITE_XML,
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


class TestOnlyTopAtOneDiverges:
    """scheme_a matches the (implicit) host convention (no top_at_one);
    scheme_b declares top_at_one = True. Neither kind nor units mismatch,
    isolating the flip on its own."""

    def test_scheme_a_gets_unflipped_value(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_scheme_meta("scheme_a"), _scheme_meta("scheme_b", top_at_one=True)],
        )
        fn = _fn_body(fortran, "test_suite_suite_physics")
        call_a = next(line for line in fn.splitlines() if "call scheme_a_run" in line)
        assert "_vert_flip" not in call_a

    def test_scheme_b_gets_flipped_value(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_scheme_meta("scheme_a"), _scheme_meta("scheme_b", top_at_one=True)],
        )
        fn = _fn_body(fortran, "test_suite_suite_physics")
        call_b = next(line for line in fn.splitlines() if "call scheme_b_run" in line)
        assert "_vert_flip" in call_b
        assert ":1:-1" in fn

    def test_write_back_restores_original_order(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_scheme_meta("scheme_a"), _scheme_meta("scheme_b", top_at_one=True)],
        )
        fn = _fn_body(fortran, "test_suite_suite_physics")
        assert "deallocate(" in fn
        lines = fn.splitlines()
        call_idx = next(i for i, line in enumerate(lines) if "call scheme_b_run" in line)
        lines_after_call = lines[call_idx + 1:]
        writeback = next(
            line for line in lines_after_call
            if ":1:-1" in line and "allocate" not in line
        )
        assert "=" in writeback

    def test_no_duplicate_declarations(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_scheme_meta("scheme_a"), _scheme_meta("scheme_b", top_at_one=True)],
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


class TestKindUnitsAndFlipChainTogether:
    """scheme_a matches the host exactly; scheme_b diverges on kind, units,
    AND top_at_one simultaneously, mirroring examples/var_compat's real
    effrs_inout case. The forward chain must apply kind, then units, then
    flip; the write-back must undo flip, then units, then kind."""

    def test_chain_applies_in_order(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [
                _scheme_meta("scheme_a"),
                _scheme_meta("scheme_b", top_at_one=True, units="cm", kind="8"),
            ],
        )
        fn = _fn_body(fortran, "test_suite_suite_physics")
        call_b = next(line for line in fn.splitlines() if "call scheme_b_run" in line)
        assert "_vert_flip" in call_b
        assert "real(" in fn
        assert "kind=8" in fn
        assert "* 100.0" in fn
        assert ":1:-1" in fn

    def test_no_duplicate_declarations(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [
                _scheme_meta("scheme_a"),
                _scheme_meta("scheme_b", top_at_one=True, units="cm", kind="8"),
            ],
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


class TestOptionalArgWithTopAtOneDivergence:
    """Regression test for a real gap found while scoping task #46: the
    vertical-flip printer (CCPPVerticalFlipOp/CCPPVerticalFlipWriteBackOp)
    had no present()-gating for an optional array, unlike the sibling
    CCPPKindCastOp/CCPPUnitConvertOp printers -- a latent crash risk (an
    absent optional array has no bounds to call size() on) for any
    divergent-std-name arg that is also declared optional, since
    suite_cap.py's own _apply_divergent_marshaling doesn't exclude optional
    args from the top_at_one branch. Not exercised by any existing example
    (none combine optional with a divergent top_at_one arg), but confirmed
    reachable via this fixture."""

    def test_flip_is_gated_on_present(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [
                _scheme_meta("scheme_a", optional=True),
                _scheme_meta("scheme_b", top_at_one=True, optional=True),
            ],
        )
        fn = _fn_body(fortran, "test_suite_suite_physics")
        call_b = next(line for line in fn.splitlines() if "call scheme_b_run" in line)
        assert "_vert_flip" in call_b
        lines = fn.splitlines()
        flip_alloc_idx = next(
            i for i, line in enumerate(lines) if "_vert_flip" in line and "allocate" in line
        )
        # The allocate+flip must be wrapped in a present() guard, same as
        # the sibling kind/unit conversions immediately preceding it.
        preceding = lines[:flip_alloc_idx]
        guard_idx = next(
            i for i in range(len(preceding) - 1, -1, -1)
            if "if (present(" in preceding[i] or preceding[i].strip() == "end if"
        )
        assert "if (present(" in preceding[guard_idx]
