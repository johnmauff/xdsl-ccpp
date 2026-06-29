"""Unit tests for nested DDT code generation.

Verifies that the cap generator correctly resolves multi-level DDT access paths.
When a scheme argument is matched to a host variable that is a member of a DDT
which is itself a member of another DDT, the generated Fortran should use the
full chain accessor (e.g. ``phys_state%rad%temperature``) rather than a
single-level path.

Also verifies as a regression that single-level DDT access (e.g.
``phys_state%temperature``) continues to work correctly.
"""

import pytest
from io import StringIO

from xdsl.context import Context
from xdsl.dialects.builtin import ModuleOp
from xdsl.universe import Universe

from xdsl_ccpp.dialects.ccpp import CCPP
from xdsl_ccpp.dialects.ccpp_utils import CCPPUtils
from xdsl_ccpp.frontend.ccpp_xml import XMLSuite, ccppXML
from xdsl_ccpp.transforms.suite_meta import MetaCAP
from xdsl_ccpp.transforms.suite_kinds import MetaKind
from xdsl_ccpp.transforms.host_var_match_pass import HostVariableMatchPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.generate_kinds import GenerateKinds
from xdsl_ccpp.transforms.strip_ccpp import StripCCPP
from xdsl_ccpp.backend.print_ftn import print_to_ftn

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml


# ── Pipeline helper ───────────────────────────────────────────────────────────

def _make_context() -> Context:
    ctx = Context()
    for name, factory in Universe.get_multiverse().all_dialects.items():
        ctx.register_dialect(name, factory)
    ctx.load_dialect(CCPP)
    ctx.load_dialect(CCPPUtils)
    return ctx


def _run_pipeline(
    tmp_path,
    suite_xml: str,
    scheme_metas: list[str],
    host_metas: list[str],
) -> str:
    """Run the full cap-gen pipeline and return the Fortran output as a string."""
    ctx = _make_context()
    frontend = ccppXML()
    ir_ops = []

    suite_file = tmp_path / "suite.xml"
    suite_file.write_text(suite_xml)
    ir_ops.append(frontend.build_suite_ir(XMLSuite(str(suite_file))))

    for i, content in enumerate(scheme_metas):
        path = tmp_path / f"scheme_{i}.meta"
        path.write_text(content)
        for meta in frontend.parse_metadata_file(str(path), True):
            ir_ops.append(frontend.build_meta_ir(meta))

    for i, content in enumerate(host_metas):
        path = tmp_path / f"host_{i}.meta"
        path.write_text(content)
        for meta in frontend.parse_metadata_file(str(path), False):
            ir_ops.append(frontend.build_meta_ir(meta))

    module = ModuleOp(ir_ops)
    for pass_cls in [MetaCAP, MetaKind, HostVariableMatchPass,
                     SuiteCAP, CCPPCAP, GenerateKinds, StripCCPP]:
        pass_cls().apply(ctx, module)

    output = StringIO()
    print_to_ftn(module, output)
    return output.getvalue()


# ── Shared scheme meta ────────────────────────────────────────────────────────

# A simple scheme with one scalar physics variable (air_temperature).
_SCHEME = f"""\
[ccpp-table-properties]
  name = temp_scheme
  type = scheme
[ccpp-arg-table]
  name = temp_scheme_run
  type = scheme
[ t ]
  standard_name = air_temperature
  type = real
  kind = kind_phys
  units = K
  intent = inout
  dimensions = ()
{CCPP_MANDATORY_ARGS}"""


# ── Nested DDT metadata (two levels: outer_type → inner_type → temperature) ──

# Leaf DDT: contains the actual physics variable.
_INNER_DDT = """\
[ccpp-table-properties]
  name = inner_type
  type = ddt
[ccpp-arg-table]
  name = inner_type
  type = ddt
[ temperature ]
  standard_name = air_temperature
  type = real
  kind = kind_phys
  units = K
  dimensions = ()
"""

# Outer DDT: contains inner_type as member 'rad'.
_OUTER_DDT = """\
[ccpp-table-properties]
  name = outer_type
  type = ddt
[ccpp-arg-table]
  name = outer_type
  type = ddt
[ rad ]
  standard_name = radiation_state_ddt
  type = inner_type
  units = DDT
  dimensions = ()
"""

# Module with a single instance of outer_type named 'phys_state'.
_MODULE_NESTED = """\
[ccpp-table-properties]
  name = phys_mod
  type = module
[ccpp-arg-table]
  name = phys_mod
  type = module
[ phys_state ]
  standard_name = physics_state_instance
  type = outer_type
  units = DDT
  dimensions = ()
"""


# ── Single-level DDT metadata (one level: flat_type → temperature) ───────────

# A DDT that directly contains the physics variable (no nesting).
_FLAT_DDT = """\
[ccpp-table-properties]
  name = flat_type
  type = ddt
[ccpp-arg-table]
  name = flat_type
  type = ddt
[ temperature ]
  standard_name = air_temperature
  type = real
  kind = kind_phys
  units = K
  dimensions = ()
"""

# Module with a single instance of flat_type named 'phys_state'.
_MODULE_FLAT = """\
[ccpp-table-properties]
  name = phys_mod
  type = module
[ccpp-arg-table]
  name = phys_mod
  type = module
[ phys_state ]
  standard_name = physics_state_instance
  type = flat_type
  units = DDT
  dimensions = ()
"""


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def nested_ddt_ftn(tmp_path_factory) -> str:
    """Fortran output for a suite where the scheme variable is in a nested DDT."""
    tmp = tmp_path_factory.mktemp("nested_ddt")
    return _run_pipeline(
        tmp,
        suite_xml=minimal_suite_xml("temp_scheme"),
        scheme_metas=[_SCHEME],
        host_metas=[_INNER_DDT, _OUTER_DDT, _MODULE_NESTED],
    )


@pytest.fixture(scope="module")
def flat_ddt_ftn(tmp_path_factory) -> str:
    """Fortran output for a suite where the scheme variable is in a single-level DDT."""
    tmp = tmp_path_factory.mktemp("flat_ddt")
    return _run_pipeline(
        tmp,
        suite_xml=minimal_suite_xml("temp_scheme"),
        scheme_metas=[_SCHEME],
        host_metas=[_FLAT_DDT, _MODULE_FLAT],
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestNestedDDTCodeGeneration:
    """The cap generator emits the full chain accessor for nested DDT variables."""

    def test_two_level_accessor_in_ccpp_cap(self, nested_ddt_ftn):
        """Scheme arg in inner DDT generates instance%outer_member%inner_member."""
        assert "phys_state%rad%temperature" in nested_ddt_ftn

    def test_module_use_statement_emitted(self, nested_ddt_ftn):
        """A USE statement for the module containing the top-level instance is emitted."""
        assert "use phys_mod, only: phys_state" in nested_ddt_ftn

    def test_no_spurious_single_level_path(self, nested_ddt_ftn):
        """A flat phys_state%temperature path is NOT emitted (that would be wrong)."""
        # The cap should use the two-level path, not a one-level shortcut.
        lines_with_accessor = [
            line for line in nested_ddt_ftn.splitlines()
            if "phys_state%" in line
        ]
        for line in lines_with_accessor:
            assert "phys_state%rad%temperature" in line, (
                f"Expected two-level accessor but found: {line!r}"
            )


class TestSingleLevelDDTRegression:
    """Single-level DDT access continues to work correctly after the nested fix."""

    def test_single_level_accessor_in_ccpp_cap(self, flat_ddt_ftn):
        """Scheme arg in a flat DDT still generates instance%member (one level)."""
        assert "phys_state%temperature" in flat_ddt_ftn

    def test_module_use_statement_emitted(self, flat_ddt_ftn):
        """A USE statement for the module containing the instance is emitted."""
        assert "use phys_mod, only: phys_state" in flat_ddt_ftn
