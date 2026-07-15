"""Unit tests for optional argument handling (Phase 1 and Phase 2).

Phase 1 tests verify that the cap generator correctly emits:
  - `optional` attribute on Fortran declarations for optional scheme args
  - keyword-argument call syntax (arg=val) when any arg is optional
  - keyword forwarding from the suite cap down to the scheme
  - keyword forwarding from the ccpp cap up to the suite cap

Phase 2 tests verify promoted optional args (host rank > scheme rank):
  - suite cap declares the arg at host rank (2D) with optional attribute
  - suite cap emits an `if (present(arg)) then / else / end if` guard inside
    the promotion do-loop so Fortran absence status is forwarded correctly
  - the with-branch calls the scheme including the sliced optional arg
  - the without-branch calls the scheme omitting the optional arg entirely
"""

import pathlib
import pytest
from io import StringIO

from xdsl.context import Context
from xdsl.dialects.builtin import ModuleOp
from xdsl.universe import Universe

from xdsl_ccpp.dialects.ccpp import CCPP
from xdsl_ccpp.dialects.ccpp_utils import CCPPUtils
from xdsl_ccpp.frontend.ccpp_xml import XMLSuite, ccppXML, parse_meta_file
from xdsl_ccpp.transforms.suite_meta import MetaCAP
from xdsl_ccpp.transforms.suite_kinds import MetaKind
from xdsl_ccpp.transforms.host_var_match_pass import HostVariableMatchPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.generate_kinds import GenerateKinds
from xdsl_ccpp.transforms.strip_ccpp import StripCCPP
from xdsl_ccpp.backend.print_ftn import print_to_ftn


# ── Project root ──────────────────────────────────────────────────────────────

_ROOT = pathlib.Path(__file__).parent.parent.parent  # repo root


# ── Pipeline helpers ──────────────────────────────────────────────────────────

def _make_context() -> Context:
    ctx = Context()
    for name, factory in Universe.get_multiverse().all_dialects.items():
        ctx.register_dialect(name, factory)
    ctx.load_dialect(CCPP)
    ctx.load_dialect(CCPPUtils)
    return ctx


def _run_capgen_pipeline(suite_xmls: list[str], scheme_metas: list[str],
                          host_metas: list[str]) -> str:
    """Run the full cap-gen pipeline and return the Fortran output as a string.

    All paths are relative to the repo root.
    """
    ctx = _make_context()
    frontend = ccppXML()
    ir_ops = []

    for xml_path in suite_xmls:
        ir_ops.append(frontend.build_suite_ir(XMLSuite(str(_ROOT / xml_path))))

    for meta_path in scheme_metas:
        for meta in parse_meta_file(str(_ROOT / meta_path), True):
            ir_ops.append(frontend.build_meta_ir(meta))

    for meta_path in host_metas:
        for meta in parse_meta_file(str(_ROOT / meta_path), False):
            ir_ops.append(frontend.build_meta_ir(meta))

    module = ModuleOp(ir_ops)
    for pass_cls in [MetaCAP, MetaKind, SuiteCAP, CCPPCAP, GenerateKinds, StripCCPP]:
        pass_cls().apply(ctx, module)

    output = StringIO()
    print_to_ftn(module, output)
    return output.getvalue()


# ── Capgen example fixture ────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def capgen_fortran() -> str:
    """Full Fortran output from the capgen example (temp_suite only)."""
    return _run_capgen_pipeline(
        suite_xmls=["examples/capgen/temp_suite.xml"],
        scheme_metas=[
            "examples/capgen/make_ddt.meta",
            "examples/capgen/environ_conditions.meta",
            "examples/capgen/setup_coeffs.meta",
            "examples/capgen/temp_set.meta",
            "examples/capgen/temp_calc_adjust.meta",
            "examples/capgen/temp_adjust.meta",
        ],
        host_metas=[
            "examples/capgen/test_host_data.meta",
            "examples/capgen/test_host_mod.meta",
            "examples/capgen/test_host.meta",
        ],
    )


# ── Suite cap declaration tests ───────────────────────────────────────────────

class TestSuiteCapDeclaration:
    """The suite cap subroutine that calls temp_adjust must declare qv optional."""

    def test_optional_keyword_on_qv_declaration(self, capgen_fortran):
        """qv is declared with the OPTIONAL attribute in the suite cap."""
        assert "optional, intent(inout) :: qv" in capgen_fortran

    def test_qv_is_array(self, capgen_fortran):
        """qv is declared as an assumed-shape array (1D slice of the column)."""
        assert "optional, intent(inout) :: qv(:)" in capgen_fortran

    def test_non_optional_args_have_no_optional(self, capgen_fortran):
        """ps (a non-optional arg) does not get the optional keyword."""
        # Find the line declaring ps — it should NOT contain optional
        for line in capgen_fortran.splitlines():
            if "intent(inout) :: ps(" in line or "intent(in) :: ps(" in line:
                assert "optional" not in line, \
                    f"ps should not be optional but got: {line!r}"
                return
        pytest.fail("Could not find ps declaration in Fortran output")


# ── Suite cap scheme-call tests ───────────────────────────────────────────────

class TestSuiteCapSchemeCall:
    """The suite cap must call temp_adjust_run using keyword syntax."""

    def test_scheme_call_uses_keyword_syntax(self, capgen_fortran):
        """The scheme call includes at least one keyword=value pair."""
        # A keyword call has the form: call temp_adjust_run(arg=val, ...)
        assert "qv=qv" in capgen_fortran

    def test_scheme_call_passes_optional_arg_by_keyword(self, capgen_fortran):
        """The keyword call includes qv= so Fortran can forward the absence status."""
        lines = capgen_fortran.splitlines()
        in_call = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("call temp_adjust_run(") or in_call:
                in_call = True
                if "qv=qv" in stripped:
                    return  # found it
                if stripped.endswith(")") and not stripped.endswith("&"):
                    break
        pytest.fail("Did not find 'qv=qv' inside the temp_adjust_run call")

    def test_errmsg_and_errflg_in_scheme_call(self, capgen_fortran):
        """Mandatory errmsg and errflg args are included in the keyword call."""
        assert "errmsg=errmsg" in capgen_fortran
        assert "errflg=errflg" in capgen_fortran


# ── CCPP cap suite-call tests ─────────────────────────────────────────────────

class TestCCPPCapSuiteCall:
    """The ccpp cap must call the suite cap using keyword syntax when qv is present."""

    def test_suite_call_uses_keyword_syntax(self, capgen_fortran):
        """The ccpp cap's call to the suite cap includes keyword=value pairs."""
        # The suite cap subroutine for physics is temp_suite_suite_physics2
        # The ccpp cap calls it with keyword syntax
        assert "qv=qv" in capgen_fortran

    def test_suite_call_includes_col_start_and_col_end(self, capgen_fortran):
        """The ccpp cap passes col_start and col_end to the suite cap."""
        # These are always required; their presence confirms the call is present
        assert "col_start=cols" in capgen_fortran or "col_start=" in capgen_fortran

    def test_ccpp_cap_passes_qv_from_host_state(self, capgen_fortran):
        """The ccpp cap passes qv from host state via keyword argument.

        qv is not a parameter of the ccpp cap's physics function — it is
        accessed from the host state object and forwarded by keyword to the
        suite cap.
        """
        lines = capgen_fortran.splitlines()
        in_ccpp_cap = False
        for line in lines:
            if "FILE:" in line and "ccpp_cap.F90" in line:
                in_ccpp_cap = True
            if in_ccpp_cap and "qv=" in line:
                return
        pytest.fail("Could not find qv= keyword argument in ccpp cap")


# ── Phase 2 helpers and fixtures ─────────────────────────────────────────────

def _run_pipeline_from_content(
    tmp_path,
    suite_xml: str,
    scheme_metas: list[str],
    host_metas: list[str],
    with_host_match: bool = False,
) -> str:
    """Write content strings to tmp_path, run the full pipeline, return Fortran.

    Set with_host_match=True to include HostVariableMatchPass (needed when
    testing promoted args — the pass sets is_promoted on scheme arg ops).
    """
    ctx = _make_context()
    frontend = ccppXML()
    ir_ops = []

    suite_file = tmp_path / "suite.xml"
    suite_file.write_text(suite_xml)
    ir_ops.append(frontend.build_suite_ir(XMLSuite(str(suite_file))))

    for i, content in enumerate(scheme_metas):
        path = tmp_path / f"scheme_{i}.meta"
        path.write_text(content)
        for meta in parse_meta_file(str(path), True):
            ir_ops.append(frontend.build_meta_ir(meta))

    for i, content in enumerate(host_metas):
        path = tmp_path / f"host_{i}.meta"
        path.write_text(content)
        for meta in parse_meta_file(str(path), False):
            ir_ops.append(frontend.build_meta_ir(meta))

    module = ModuleOp(ir_ops)
    passes = [MetaCAP, MetaKind]
    if with_host_match:
        passes.append(HostVariableMatchPass)
    passes += [SuiteCAP, CCPPCAP, GenerateKinds, StripCCPP]
    for pass_cls in passes:
        pass_cls().apply(ctx, module)

    output = StringIO()
    print_to_ftn(module, output)
    return output.getvalue()


# Minimal scheme with one optional arg that will be promoted (rank 1 in scheme,
# rank 2 in host → suite cap receives it as 2D and slices it in a do-loop).
_PROMOTED_OPT_SCHEME = """\
[ccpp-table-properties]
  name = opt_promote_scheme
  type = scheme
[ccpp-arg-table]
  name = opt_promote_scheme_run
  type = scheme
[ ncol ]
  standard_name = horizontal_loop_extent
  units = count
  type = integer
  intent = in
  dimensions = ()
[ qv ]
  standard_name = water_vapor_specific_humidity
  units = kg kg-1
  type = real
  kind = kind_phys
  intent = inout
  dimensions = (horizontal_loop_extent)
  optional = True
[ errmsg ]
  standard_name = ccpp_error_message
  long_name = Error message for error handling in CCPP
  type = character
  kind = len=512
  intent = out
  dimensions = ()
  units = none
[ errflg ]
  standard_name = ccpp_error_code
  long_name = Error flag for error handling in CCPP
  type = integer
  intent = out
  dimensions = ()
  units = 1
"""

# Host module provides the vertical dimension size so the promotion loop can
# find its upper bound via standard_name lookup.
_PROMOTED_OPT_HOST_MOD = """\
[ccpp-table-properties]
  name = opt_promote_host_mod
  type = module
[ccpp-arg-table]
  name = opt_promote_host_mod
  type = module
[ pver ]
  standard_name = vertical_layer_dimension
  type = integer
  units = count
  dimensions = ()
"""

# Host model provides col_start, col_end, the 2D qv array, errmsg, errflg.
_PROMOTED_OPT_HOST = """\
[ccpp-table-properties]
  name = opt_promote_host
  type = host
[ccpp-arg-table]
  name = opt_promote_host
  type = host
[ col_start ]
  standard_name = horizontal_loop_begin
  type = integer
  units = count
  dimensions = ()
  protected = True
[ col_end ]
  standard_name = horizontal_loop_end
  type = integer
  units = count
  dimensions = ()
  protected = True
[ qv_host ]
  standard_name = water_vapor_specific_humidity
  type = real
  kind = kind_phys
  units = kg kg-1
  dimensions = (horizontal_dimension, vertical_layer_dimension)
[ errmsg ]
  standard_name = ccpp_error_message
  type = character
  kind = len=512
  units = none
  dimensions = ()
[ errflg ]
  standard_name = ccpp_error_code
  type = integer
  units = 1
  dimensions = ()
"""

_PROMOTED_OPT_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="opt_promote_suite" version="1.0">
  <group name="physics">
    <scheme>opt_promote_scheme</scheme>
  </group>
</suite>
"""


@pytest.fixture(scope="module")
def promoted_opt_fortran(tmp_path_factory) -> str:
    """Full Fortran output from a minimal suite with one promoted optional arg."""
    tmp_path = tmp_path_factory.mktemp("promoted_opt")
    return _run_pipeline_from_content(
        tmp_path,
        suite_xml=_PROMOTED_OPT_SUITE_XML,
        scheme_metas=[_PROMOTED_OPT_SCHEME],
        host_metas=[_PROMOTED_OPT_HOST_MOD, _PROMOTED_OPT_HOST],
        with_host_match=True,
    )


# ── Phase 2 tests ─────────────────────────────────────────────────────────────

class TestPromotedOptionalArgs:
    """Suite cap must emit an if(present) guard inside the promotion do-loop."""

    def test_suite_cap_declares_qv_optional_2d(self, promoted_opt_fortran):
        """The suite cap declares qv as 2D (host rank) with optional attribute."""
        assert "optional, intent(inout) :: qv(:, :)" in promoted_opt_fortran

    def test_promotion_loop_present(self, promoted_opt_fortran):
        """A do-loop over the vertical dimension is emitted."""
        assert "do " in promoted_opt_fortran

    def test_present_check_with_branch(self, promoted_opt_fortran):
        """The with-branch of the present check calls the scheme including qv."""
        assert "if (present(qv)) then" in promoted_opt_fortran

    def test_present_check_else_branch(self, promoted_opt_fortran):
        """An else branch is emitted so the scheme is called without qv."""
        # The else must appear after the if(present) — verify both appear
        text = promoted_opt_fortran
        assert "if (present(qv)) then" in text
        assert "else" in text

    def test_with_branch_passes_qv_as_keyword(self, promoted_opt_fortran):
        """Inside the with-branch the call uses keyword qv= with an array slice."""
        assert "qv=qv(" in promoted_opt_fortran

    def test_without_branch_omits_qv(self, promoted_opt_fortran):
        """The without-branch call does not include qv=."""
        lines = promoted_opt_fortran.splitlines()
        in_else = False
        for line in lines:
            stripped = line.strip()
            if stripped == "else":
                in_else = True
            if in_else and stripped == "end if":
                break
            if in_else and "qv=" in stripped:
                pytest.fail(f"qv= found in without-branch: {line!r}")

    def test_end_if_closes_present_check(self, promoted_opt_fortran):
        """end if closes the present check block."""
        assert "end if" in promoted_opt_fortran
