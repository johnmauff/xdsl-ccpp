"""Unit tests for ccpp_t threading through generated cap subroutines.

Verifies that when a host metadata table declares a variable with
``standard_name = ccpp_t_instance`` and ``type = ccpp_t``, the generated
suite cap and ccpp cap subroutines include ``ccpp_data`` (or whatever the
local variable name is) as an ``intent(inout)`` argument, and that the
ccpp_suite_state guard is emitted as a per-instance array indexed by
``ccpp_data%ccpp_instance``.
"""

from io import StringIO

import pytest

from xdsl.dialects import builtin, func, memref
from xdsl.ir import Operation
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp_utils import DerivedType
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.suite_cap import SuiteCAP
from xdsl_ccpp.transforms.suite_meta import MetaCAP
from xdsl_ccpp.transforms.host_var_match_pass import HostVariableMatchPass
from xdsl_ccpp.transforms.generate_kinds import GenerateKinds
from xdsl_ccpp.transforms.suite_kinds import MetaKind
from xdsl_ccpp.transforms.strip_ccpp import StripCCPP
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.util.ccpp_conventions import CCPP_NUM_INSTANCES

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml


# ── metadata fixtures ─────────────────────────────────────────────────────────

_HOST_CCPP_T_VAR = """\
[ ccpp_data ]
  standard_name = ccpp_t_instance
  long_name = instance of derived data type ccpp_t
  units = DDT
  dimensions = ()
  type = ccpp_t
"""

_SCHEME_REAL_VAR = """\
[ temperature ]
  standard_name = air_temperature
  long_name = air temperature
  units = K
  dimensions = (horizontal_loop_extent,vertical_layer_dimension)
  type = real
  kind = kind_phys
  intent = in
"""

_HOST_REAL_VAR = """\
[ temp ]
  standard_name = air_temperature
  long_name = air temperature
  units = K
  dimensions = (horizontal_dimension,vertical_layer_dimension)
  type = real
  kind = kind_phys
"""


def _scheme_meta(name: str, extra_args: str = "") -> str:
    return f"""\
[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_run
  type = scheme
{extra_args}
{CCPP_MANDATORY_ARGS}
"""


def _host_meta(module_name: str, extra_args: str = "") -> str:
    return f"""\
[ccpp-table-properties]
  name = {module_name}
  type = host
[ccpp-arg-table]
  name = {module_name}
  type = host
{extra_args}
"""


def _run_full_pipeline(run_host_match, ccpp_context, scheme_metas, host_metas, suite_xml,
                       num_instances=None):
    """Run MetaCAP + HostVariableMatchPass + SuiteCAP + CCPPCAP."""
    module = run_host_match(scheme_metas=scheme_metas, host_metas=host_metas,
                            suite_xml=suite_xml)
    suite_cap = SuiteCAP(num_instances=num_instances) if num_instances is not None else SuiteCAP()
    suite_cap.apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    return module


def _fortran_output(run_host_match, ccpp_context, scheme_metas, host_metas, suite_xml,
                    num_instances=None) -> str:
    """Run the full pipeline through the Fortran printer and return the output."""
    module = _run_full_pipeline(run_host_match, ccpp_context, scheme_metas, host_metas,
                                suite_xml, num_instances=num_instances)
    for pass_cls in [MetaKind, GenerateKinds, StripCCPP]:
        pass_cls().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _find_public_fns(module):
    """Return all public FuncOps from generated named modules as {name: fn}."""
    result = {}
    for op in module.body.ops:
        if not (isa(op, builtin.ModuleOp) and op.sym_name is not None):
            continue
        for child in op.body.block.ops:
            if (
                isa(child, func.FuncOp)
                and not child.is_declaration
                and child.sym_visibility is not None
                and child.sym_visibility.data == "public"
            ):
                result[child.sym_name.data] = child
    return result


def _has_ccpp_t_arg(fn: func.FuncOp) -> bool:
    """Return True if any block arg is a memref<ccpp_t>."""
    ccpp_t_type = memref.MemRefType(DerivedType("ccpp_t"), [])
    for arg in fn.body.block.args:
        if arg.type == ccpp_t_type:
            return True
    return False


def _ccpp_t_is_inout(fn: func.FuncOp) -> bool:
    """Return True if a ccpp_t block arg appears in the function's ReturnOp."""
    ccpp_t_type = memref.MemRefType(DerivedType("ccpp_t"), [])
    ccpp_t_arg = None
    for arg in fn.body.block.args:
        if arg.type == ccpp_t_type:
            ccpp_t_arg = arg
            break
    if ccpp_t_arg is None:
        return False
    for op in fn.body.block.ops:
        if isa(op, func.ReturnOp):
            return any(v is ccpp_t_arg for v in op.operands)
    return False


# ── tests ─────────────────────────────────────────────────────────────────────

class TestCcppTThreading:
    """ccpp_t is threaded through suite cap and ccpp cap subroutines."""

    def test_suite_cap_has_ccpp_t_arg(self, run_host_match, ccpp_context):
        """Suite cap run subroutine includes ccpp_t as a block argument."""
        module = _run_full_pipeline(
            run_host_match, ccpp_context,
            scheme_metas=[_scheme_meta("test_scheme", _SCHEME_REAL_VAR)],
            host_metas=[_host_meta("test_mod", _HOST_REAL_VAR + _HOST_CCPP_T_VAR)],
            suite_xml=minimal_suite_xml("test_scheme"),
        )
        fns = _find_public_fns(module)
        run_fn = fns.get("test_suite_suite_physics")
        assert run_fn is not None, f"Expected test_suite_suite_physics; found: {list(fns)}"
        assert _has_ccpp_t_arg(run_fn), "Suite cap run fn should have ccpp_t block arg"

    def test_suite_cap_ccpp_t_is_inout(self, run_host_match, ccpp_context):
        """The ccpp_t arg in suite cap appears in ReturnOp (intent inout)."""
        module = _run_full_pipeline(
            run_host_match, ccpp_context,
            scheme_metas=[_scheme_meta("test_scheme", _SCHEME_REAL_VAR)],
            host_metas=[_host_meta("test_mod", _HOST_REAL_VAR + _HOST_CCPP_T_VAR)],
            suite_xml=minimal_suite_xml("test_scheme"),
        )
        fns = _find_public_fns(module)
        run_fn = fns["test_suite_suite_physics"]
        assert _ccpp_t_is_inout(run_fn), "ccpp_t arg should be intent(inout) in suite cap"

    def test_ccpp_cap_run_has_ccpp_t_arg(self, run_host_match, ccpp_context):
        """CCPP cap run function includes ccpp_t as a block argument."""
        module = _run_full_pipeline(
            run_host_match, ccpp_context,
            scheme_metas=[_scheme_meta("test_scheme", _SCHEME_REAL_VAR)],
            host_metas=[_host_meta("test_mod", _HOST_REAL_VAR + _HOST_CCPP_T_VAR)],
            suite_xml=minimal_suite_xml("test_scheme"),
        )
        fns = _find_public_fns(module)
        run_fn = next(
            (fn for name, fn in fns.items() if name.endswith("_ccpp_physics_run")),
            None,
        )
        assert run_fn is not None, f"No _ccpp_physics_run fn found; fns: {list(fns)}"
        assert _has_ccpp_t_arg(run_fn), "CCPP cap run fn should have ccpp_t block arg"

    def test_ccpp_cap_lifecycle_has_ccpp_t_arg(self, run_host_match, ccpp_context):
        """CCPP cap initialize function includes ccpp_t as a block argument."""
        module = _run_full_pipeline(
            run_host_match, ccpp_context,
            scheme_metas=[_scheme_meta("test_scheme", _SCHEME_REAL_VAR)],
            host_metas=[_host_meta("test_mod", _HOST_REAL_VAR + _HOST_CCPP_T_VAR)],
            suite_xml=minimal_suite_xml("test_scheme"),
        )
        fns = _find_public_fns(module)
        init_fn = next(
            (fn for name, fn in fns.items() if name.endswith("_ccpp_physics_initialize")),
            None,
        )
        assert init_fn is not None, f"No _ccpp_physics_initialize fn found; fns: {list(fns)}"
        assert _has_ccpp_t_arg(init_fn), "CCPP cap init fn should have ccpp_t block arg"

    def test_no_ccpp_t_without_handle(self, run_host_match, ccpp_context):
        """Without ccpp_t in host metadata, no ccpp_t args appear in caps."""
        module = _run_full_pipeline(
            run_host_match, ccpp_context,
            scheme_metas=[_scheme_meta("test_scheme", _SCHEME_REAL_VAR)],
            host_metas=[_host_meta("test_mod", _HOST_REAL_VAR)],
            suite_xml=minimal_suite_xml("test_scheme"),
        )
        fns = _find_public_fns(module)
        for name, fn in fns.items():
            assert not _has_ccpp_t_arg(fn), \
                f"Function {name} should not have ccpp_t arg when no CcppHandleOp"


class TestCcppTFortranOutput:
    """Generated Fortran correctly reflects per-instance ccpp_suite_state."""

    def test_state_array_declaration(self, run_host_match, ccpp_context):
        """ccpp_suite_state is declared as dimension(200) when ccpp_t is present."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            scheme_metas=[_scheme_meta("test_scheme", _SCHEME_REAL_VAR)],
            host_metas=[_host_meta("test_mod", _HOST_REAL_VAR + _HOST_CCPP_T_VAR)],
            suite_xml=minimal_suite_xml("test_scheme"),
        )
        assert f"dimension({CCPP_NUM_INSTANCES})" in fortran
        assert "ccpp_suite_state" in fortran

    def test_state_guard_uses_instance_index(self, run_host_match, ccpp_context):
        """State comparison in guard references ccpp_suite_state(ccpp_data%ccpp_instance)."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            scheme_metas=[_scheme_meta("test_scheme", _SCHEME_REAL_VAR)],
            host_metas=[_host_meta("test_mod", _HOST_REAL_VAR + _HOST_CCPP_T_VAR)],
            suite_xml=minimal_suite_xml("test_scheme"),
        )
        assert "ccpp_suite_state(ccpp_data%ccpp_instance)" in fortran

    def test_state_assignment_uses_instance_index(self, run_host_match, ccpp_context):
        """State assignment targets ccpp_suite_state(ccpp_data%ccpp_instance)."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            scheme_metas=[_scheme_meta("test_scheme", _SCHEME_REAL_VAR)],
            host_metas=[_host_meta("test_mod", _HOST_REAL_VAR + _HOST_CCPP_T_VAR)],
            suite_xml=minimal_suite_xml("test_scheme"),
        )
        # Assignment to the state variable must carry the instance index
        assert "ccpp_suite_state(ccpp_data%ccpp_instance) =" in fortran

    def test_scalar_state_without_ccpp_t(self, run_host_match, ccpp_context):
        """Without ccpp_t, ccpp_suite_state remains a scalar (no dimension attribute)."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            scheme_metas=[_scheme_meta("test_scheme", _SCHEME_REAL_VAR)],
            host_metas=[_host_meta("test_mod", _HOST_REAL_VAR)],
            suite_xml=minimal_suite_xml("test_scheme"),
        )
        assert f"dimension({CCPP_NUM_INSTANCES})" not in fortran
        assert "ccpp_suite_state" in fortran
