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
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.generate_kinds import GenerateKinds
from xdsl_ccpp.transforms.strip_ccpp import StripCCPP
from xdsl_ccpp.backend.print_ftn import print_to_ftn


@pytest.fixture(scope="module", autouse=True)
def _legacy_mode(legacy_mode_module):
    """Module-scoped, autouse: this file's own module-scoped fixtures build
    IR (and construct ArgumentOps) eagerly, so a plain function-scoped
    usefixtures("legacy_mode") would activate too late for them -- autouse
    fixtures are set up before explicitly-requested ones of the same scope.
    """


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
    for pass_cls in [MetaCAP, ArgOwnershipPass, MetaKind, SuiteCAP, CCPPCAP,
                     GenerateKinds, StripCCPP]:
        pass_cls().apply(ctx, module)

    output = StringIO()
    print_to_ftn(module, output)
    return output.getvalue()


# ── Capgen example fixture ────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def capgen_fortran() -> str:
    """Full Fortran output from the capgen example (temp_suite only)."""
    return _run_capgen_pipeline(
        suite_xmls=["examples/capgen/scheme/temp_suite.xml"],
        scheme_metas=[
            "examples/capgen/scheme/make_ddt.meta",
            "examples/capgen/scheme/environ_conditions.meta",
            "examples/capgen/scheme/setup_coeffs.meta",
            "examples/capgen/scheme/temp_set.meta",
            "examples/capgen/scheme/temp_calc_adjust.meta",
            "examples/capgen/scheme/temp_adjust.meta",
        ],
        host_metas=[
            "examples/capgen/host_ftn/test_host_data.meta",
            "examples/capgen/host_ftn/test_host_mod.meta",
            "examples/capgen/host_ftn/test_host.meta",
        ],
    )


# ── Suite cap declaration tests ───────────────────────────────────────────────

class TestSuiteCapDeclaration:
    """The suite cap subroutine that calls temp_adjust must declare qv optional."""

    def test_optional_keyword_on_qv_declaration(self, capgen_fortran):
        """qv is declared with the OPTIONAL attribute in the suite cap."""
        assert "optional, target, intent(inout) :: qv" in capgen_fortran

    def test_qv_is_array(self, capgen_fortran):
        """qv is declared as an assumed-shape array (2D, matching real capgen-v1's
        own horizontal_dimension x vertical_layer_dimension shape)."""
        assert "optional, target, intent(inout) :: qv(:, :)" in capgen_fortran

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

    def test_physics_run_declares_col_start_and_col_end(self, capgen_fortran):
        """ccpp_physics_run always declares col_start/col_end as its own
        dispatch-level parameters, regardless of whether any scheme below it
        happens to need them forwarded (capgen's schemes now resolve their own
        per-call column count via the host-matched horizontal_dimension
        convention rather than a col_start/col_end argument threaded down
        from this level, so the two are no longer necessarily passed further
        in, but the standard framework-level signature always has them)."""
        assert "subroutine ccpp_physics_run(suite_name, suite_part, col_start, col_end" \
            in capgen_fortran

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
    passes.append(ArgOwnershipPass)
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
        assert "optional, target, intent(inout) :: qv(:, :)" in promoted_opt_fortran

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


# ── Phase 3: same promoted-optional-arg scenario, but on the current
# horizontal_dimension convention instead of the legacy horizontal_loop_extent
# one. Regression coverage for two bugs found while migrating capgen/ddthost
# off horizontal_loop_extent: _build_promoted_call_ops's block-arg branch
# unconditionally read data_ops["ccpp_lbound_one"], which was only ever
# populated by the legacy _classify_args -> _build_ncol_compute_ops path
# (KeyError under horizontal_dimension); and even once that's fixed, its
# range upper bound fell back to data_ops.get("ncol", loop_var_memref) --
# under horizontal_dimension "ncol" is never in data_ops, so it silently used
# the promotion loop's own index variable as the column upper bound, giving
# a growing 1:vertical_layer_index slice range instead of the real 1:ncol. ──

_PROMOTED_HORIZ_DIM_SCHEME = """\
[ccpp-table-properties]
  name = opt_promote_scheme_hd
  type = scheme
[ccpp-arg-table]
  name = opt_promote_scheme_hd_run
  type = scheme
[ ncol ]
  standard_name = horizontal_dimension
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
  dimensions = (horizontal_dimension)
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

_PROMOTED_HORIZ_DIM_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="opt_promote_suite_hd" version="1.0">
  <group name="physics">
    <scheme>opt_promote_scheme_hd</scheme>
  </group>
</suite>
"""

# Same as _PROMOTED_OPT_HOST_MOD plus a plain module-scope horizontal_dimension
# scalar -- every real example using this convention (hello_world_mod.meta,
# kessler_host_mod.meta, test_host_mod.meta) declares one; HostVariableMatchPass
# requires a real host match for any host_matched scalar, it does not defer
# horizontal_dimension scalars to a later col_start/col_end-derived pass.
_PROMOTED_HORIZ_DIM_HOST_MOD = """\
[ccpp-table-properties]
  name = opt_promote_host_mod_hd
  type = module
[ccpp-arg-table]
  name = opt_promote_host_mod_hd
  type = module
[ ncols ]
  standard_name = horizontal_dimension
  type = integer
  units = count
  dimensions = ()
[ pver ]
  standard_name = vertical_layer_dimension
  type = integer
  units = count
  dimensions = ()
"""


@pytest.fixture(scope="module")
def promoted_horiz_dim_fortran(tmp_path_factory) -> str:
    """Full Fortran output for the horizontal_dimension-convention promoted-arg case."""
    tmp_path = tmp_path_factory.mktemp("promoted_horiz_dim")
    return _run_pipeline_from_content(
        tmp_path,
        suite_xml=_PROMOTED_HORIZ_DIM_SUITE_XML,
        scheme_metas=[_PROMOTED_HORIZ_DIM_SCHEME],
        host_metas=[_PROMOTED_HORIZ_DIM_HOST_MOD, _PROMOTED_OPT_HOST],
        with_host_match=True,
    )


class TestPromotedArgsOnHorizontalDimension:
    """Same promoted-optional-arg behavior must hold under horizontal_dimension,
    with the column range correctly resolved (not the promotion loop index)."""

    def test_pipeline_does_not_crash(self, promoted_horiz_dim_fortran):
        """Regression test for the ccpp_lbound_one KeyError: merely building
        the fixture (see above) must not raise -- if it does, pytest reports
        the fixture error rather than reaching this test body at all."""
        assert "opt_promote_scheme_hd" in promoted_horiz_dim_fortran

    def test_lbound_one_declared_and_initialised(self, promoted_horiz_dim_fortran):
        """ccpp_lbound_one is declared and set to 1 before the promotion loop."""
        assert "integer :: ccpp_lbound_one" in promoted_horiz_dim_fortran
        assert "ccpp_lbound_one = 1" in promoted_horiz_dim_fortran

    def test_qv_slice_uses_real_ncol_not_loop_index(self, promoted_horiz_dim_fortran):
        """qv's column-range slice upper bound must be the real resolved ncol,
        not the promotion loop's own vertical-layer index variable -- the
        bug produced qv(ccpp_lbound_one:vertical_layer_index) (a range that
        grows with the loop) instead of qv(ccpp_lbound_one:ncol)."""
        text = promoted_horiz_dim_fortran
        assert "qv=qv(ccpp_lbound_one:ncol, vertical_layer_index)" in text
        assert "qv=qv(ccpp_lbound_one:vertical_layer_index, vertical_layer_index)" not in text


# Minimal non-promoted scheme with one optional arg matched against a host
# var carrying 'active = flag_for_opt_var' -- the flat-call counterpart to
# _PROMOTED_OPT_SCHEME above (examples/opt_arg's own real shape: no
# promotion involved, just a plain optional arg gated by a named host
# logical). 'nx' is mandatory so both the with- and without-branches share
# at least one real call argument, matching the real bug's own shape.
_ACTIVE_GATED_SCHEME = """\
[ccpp-table-properties]
  name = active_gated_scheme
  type = scheme
[ccpp-arg-table]
  name = active_gated_scheme_run
  type = scheme
[ nx ]
  standard_name = size_of_std_arg
  units = count
  type = integer
  intent = in
  dimensions = ()
[ opt_var ]
  standard_name = opt_arg
  units = 1
  type = integer
  intent = inout
  dimensions = (size_of_std_arg)
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

_ACTIVE_GATED_HOST = """\
[ccpp-table-properties]
  name = active_gated_host
  type = host
[ccpp-arg-table]
  name = active_gated_host
  type = host
[ nx ]
  standard_name = size_of_std_arg
  type = integer
  units = count
  dimensions = ()
[ opt_arg ]
  standard_name = opt_arg
  type = integer
  units = 1
  dimensions = (size_of_std_arg)
  active = flag_for_opt_var
[ flag_for_opt_var ]
  standard_name = flag_for_opt_var
  type = logical
  units = 1
  dimensions = ()
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

_ACTIVE_GATED_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="active_gated_suite" version="1.0">
  <group name="physics">
    <scheme>active_gated_scheme</scheme>
  </group>
</suite>
"""


@pytest.fixture(scope="module")
def active_gated_fortran(tmp_path_factory) -> str:
    """Full Fortran output for a flat (non-promoted) scheme with one
    optional arg matched against an 'active'-gated host variable."""
    tmp_path = tmp_path_factory.mktemp("active_gated")
    return _run_pipeline_from_content(
        tmp_path,
        suite_xml=_ACTIVE_GATED_SUITE_XML,
        scheme_metas=[_ACTIVE_GATED_SCHEME],
        host_metas=[_ACTIVE_GATED_HOST],
        with_host_match=True,
    )


class TestActiveGatedOptionalArgs:
    """The 'active' property (dead until this fix -- parsed into IR, never
    read by any pass) must now gate a matched optional arg's call/marshaling
    behind the host's own named logical expression, not treat it as always
    present. Distinct from TestPromotedOptionalArgs' present()-based guard:
    this is the flat (non-promotion-loop) call path, and the condition
    tested is an arbitrary host expression, not Fortran's present()
    intrinsic."""

    def test_pipeline_does_not_crash(self, active_gated_fortran):
        assert "active_gated_scheme_run" in active_gated_fortran

    def test_guard_tests_the_host_active_expression(self, active_gated_fortran):
        assert "if (flag_for_opt_var) then" in active_gated_fortran

    def test_with_branch_passes_opt_var(self, active_gated_fortran):
        text = active_gated_fortran
        with_idx = text.index("if (flag_for_opt_var) then")
        else_idx = text.index("else", with_idx)
        with_branch = text[with_idx:else_idx]
        assert "opt_var=opt_var" in with_branch

    def test_without_branch_omits_opt_var(self, active_gated_fortran):
        text = active_gated_fortran
        else_idx = text.index("else", text.index("if (flag_for_opt_var) then"))
        end_if_idx = text.index("end if", else_idx)
        without_branch = text[else_idx:end_if_idx]
        assert "call active_gated_scheme_run(" in without_branch
        assert "opt_var=opt_var" not in without_branch
        # The mandatory arg must still be passed in both branches.
        assert "nx=nx" in without_branch

    def test_flag_is_use_associated_not_threaded_as_arg(self, active_gated_fortran):
        """Stage 2a of the vocabulary-resolution redesign (ccpp_cap_refactor_plan.md):
        flag_for_opt_var is declared in a HOST-type table
        (_ACTIVE_GATED_HOST), but is real host-owned state, not a dispatch
        scalar -- resolved via use-association like a MODULE-type var,
        never threaded as a dummy argument on either the suite-cap-level
        function or the outer ccpp_physics_run wrapper."""
        text = active_gated_fortran
        assert "use active_gated_host, only: flag_for_opt_var" in text
        assert "subroutine active_gated_suite_suite_physics(nx, opt_var, errmsg, errflg)" in text
        assert (
            "subroutine ccpp_physics_run(suite_name, suite_part, nx, opt_var, "
            "errmsg, errflg)" in text
        )


# Minimal scheme whose _timestep_init entry needs a real HOST-type-table
# variable ('nx') -- examples/opt_arg's own confirmed bug shape:
# lifecycle_cap.py's _generate_lifecycle_fn hardcoded "timestep_initial has
# no host inputs", so it fell back to an uninitialized local placeholder
# (lc_nx) instead of threading the real value through. 'nx2' with a name
# ending in a digit specifically exercises the xDSL name_hint auto-strip
# gotcha (extract_valid_name silently drops a trailing "_<digits>", which
# would otherwise collide two differently-suffixed extra args down to the
# same printed name -- see lifecycle_cap.py's own "__hostarg" marker).
_TIMESTEP_HOST_ARG_SCHEME = """\
[ccpp-table-properties]
  name = timestep_host_arg_scheme
  type = scheme
[ccpp-arg-table]
  name = timestep_host_arg_scheme_timestep_init
  type = scheme
[ nx ]
  standard_name = size_of_std_arg
  units = count
  type = integer
  intent = in
  dimensions = ()
[ nx2 ]
  standard_name = size_of_std_arg_2
  units = count
  type = integer
  intent = in
  dimensions = ()
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

_TIMESTEP_HOST_ARG_HOST = """\
[ccpp-table-properties]
  name = timestep_host_arg_host
  type = host
[ccpp-arg-table]
  name = timestep_host_arg_host
  type = host
[ nx ]
  standard_name = size_of_std_arg
  type = integer
  units = count
  dimensions = ()
[ nx2 ]
  standard_name = size_of_std_arg_2
  type = integer
  units = count
  dimensions = ()
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

_TIMESTEP_HOST_ARG_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="timestep_host_arg_suite" version="1.0">
  <group name="physics">
    <scheme>timestep_host_arg_scheme</scheme>
  </group>
</suite>
"""


@pytest.fixture(scope="module")
def timestep_host_arg_fortran(tmp_path_factory) -> str:
    """Full Fortran output for a suite whose timestep_init phase needs real
    HOST-type-table data on the outer ccpp_physics_timestep_init wrapper."""
    tmp_path = tmp_path_factory.mktemp("timestep_host_arg")
    return _run_pipeline_from_content(
        tmp_path,
        suite_xml=_TIMESTEP_HOST_ARG_SUITE_XML,
        scheme_metas=[_TIMESTEP_HOST_ARG_SCHEME],
        host_metas=[_TIMESTEP_HOST_ARG_HOST],
        with_host_match=True,
    )


class TestTimestepPhaseHostTableArgs:
    """A lifecycle phase (timestep_initial/timestep_final/init/finalize)
    whose own scheme entry point needs a real HOST-type-table variable must
    expose it as a real dummy argument on the outer ccpp_physics_* wrapper,
    not fall back to an uninitialized local placeholder (lc_nx) -- the
    confirmed examples/opt_arg bug."""

    def test_pipeline_does_not_crash(self, timestep_host_arg_fortran):
        assert "timestep_host_arg_scheme" in timestep_host_arg_fortran

    def test_wrapper_signature_includes_real_args_not_placeholders(
        self, timestep_host_arg_fortran
    ):
        text = timestep_host_arg_fortran
        # Find the specific wrapper's own signature line(s).
        wrapper_idx = text.index("ccpp_physics_timestep_init(")
        sig_end = text.index(")", wrapper_idx)
        sig = text[wrapper_idx:sig_end]
        assert "nx" in sig
        assert "nx2" in sig
        assert "lc_nx" not in sig

    def test_no_disconnected_local_placeholders_declared(self, timestep_host_arg_fortran):
        """The old bug declared lc_nx/lc_nx2 as local, never-allocated
        dummies and passed those into the suite callee instead."""
        assert "lc_nx" not in timestep_host_arg_fortran

    def test_call_forwards_the_real_wrapper_args(self, timestep_host_arg_fortran):
        # timestep_host_arg_suite_suite_timestep_init_physics (task #28:
        # timestep_init is now group-scoped -- group name "physics" here),
        # not the old flat timestep_host_arg_suite_suite_timestep_initial.
        text = timestep_host_arg_fortran
        call_idx = text.index("call timestep_host_arg_suite_suite_timestep_init_physics(")
        call_end = text.index(")", call_idx)
        call = text[call_idx:call_end]
        assert "nx" in call
        assert "nx2" in call
