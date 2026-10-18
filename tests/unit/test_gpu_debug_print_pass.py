"""Unit tests for `--gpu-debug-prints` (GPUDebugPrintPass) and the
scheme-call-site-discovery machinery it shares with scheme_io_capture_pass.py.

No test file existed for this pass before -- found while extracting its
call-site-discovery machinery (_expr_text, _array_rank, _device_arg_names,
iter_scheme_call_sites, etc.) into cap_shared.py for a second consumer
(scheme_io_capture_pass.py, dup-meta-shadow-elim backlog's
`scheme-io-capture` item). Added alongside that refactor both to close the
real coverage gap and to verify the refactor itself is behavior-preserving
-- Part C's call-site walk moved from a loop nested inside the same
per-function iteration as Parts A/B to a separate, independent top-level
loop over `cap_shared.iter_scheme_call_sites`.

Covers Part A (array-size diagnostics after a device-residency-
establishing op) directly through the pass, and the shared call-site
machinery (iter_scheme_call_sites/_device_arg_names/_call_param_names/
_call_args) directly, against the real pipeline's own generated IR -- not
Part C's own pass-level output. Confirmed directly (see the real-build
investigation this file's own git history records): a minimal
single-scheme suite harness like this one never produces a *sliced*
device-resident call argument (RankReducingSliceOp) -- that only arises
in suites with real column-bound dispatch context this harness doesn't
build -- so Part C itself never fires here, which is the correct,
by-design behavior (confirmed true even for the pre-existing, proven
`test_gpu_directives.py` fixture using the identical dimension
convention), not a gap in this refactor. Testing the shared machinery
directly, rather than only through Part C's own narrower slice-only
output, is what this file's own new consumer (scheme_io_capture_pass.py)
actually needs verified anyway, since it instruments every intent-in/
out/inout argument regardless of bare-vs-sliced shape.

Part B (module-scalar diagnostics) was untouched by the refactor (still
inline in the same per-function loop, unchanged code) and isn't
separately covered here.
"""

from io import StringIO

import pytest

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.gpu_ccpp_cap_pass import GPUCcppCapPass
from xdsl_ccpp.transforms.gpu_data_pass import GPUDataPass
from xdsl_ccpp.transforms.gpu_debug_print_pass import GPUDebugPrintPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP
from xdsl_ccpp.transforms.util.cap_shared import (
    _call_args,
    _call_param_names,
    _device_arg_names,
    iter_scheme_call_sites,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import BuildMetaDataDescriptions
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module

pytestmark = pytest.mark.usefixtures("legacy_mode")

# "hosted" is host-matched and device-resident on both sides (memory_space
# = device on the scheme arg and the host var). "host_only" has no
# memory_space on either side -- _device_arg_names must still exclude it
# after the refactor.
_SCHEME_META = f"""\
[ccpp-table-properties]
  name = test_dbg_scheme
  type = scheme
[ccpp-arg-table]
  name = test_dbg_scheme_run
  type = scheme
[ hosted ]
  standard_name = test_dbg_hosted_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = inout
[ host_only ]
  standard_name = test_dbg_host_only_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = in
{CCPP_MANDATORY_ARGS}
"""

_HOST_META = """\
[ccpp-table-properties]
  name = test_dbg_host
  type = module
[ccpp-arg-table]
  name = test_dbg_host
  type = module
[ hosted ]
  standard_name = test_dbg_hosted_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
[ host_only ]
  standard_name = test_dbg_host_only_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
"""

_SUITE_XML = minimal_suite_xml("test_dbg_scheme", suite_name="test_dbg_suite")


def _build_module(run_host_match, ccpp_context):
    module = run_host_match(
        scheme_metas=[_SCHEME_META],
        host_metas=[_HOST_META],
        suite_xml=_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    GPUDataPass(directive="acc").apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    GPUCcppCapPass(directive="acc").apply(ccpp_context, module)
    return module


def _fortran_output(run_host_match, ccpp_context) -> str:
    module = _build_module(run_host_match, ccpp_context)
    GPUDebugPrintPass().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def test_part_a_array_size_diagnostic_after_residency_op(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context)
    assert "CCPPDBG array" in fortran
    assert "device size:" in fortran


def test_pass_runs_cleanly_with_no_sliced_device_args(run_host_match, ccpp_context):
    # Documents the real, correct behavior directly: a minimal single-
    # scheme suite never produces a sliced device-resident call argument,
    # so Part C's own diagnostic legitimately never fires here -- the pass
    # must still run to completion without error, not crash on finding
    # zero matching call sites.
    fortran = _fortran_output(run_host_match, ccpp_context)
    assert "CCPPDBG call-arg" not in fortran


def test_iter_scheme_call_sites_finds_the_real_call(run_host_match, ccpp_context):
    """Direct test of the shared call-site-discovery machinery -- the
    thing scheme_io_capture_pass.py actually depends on -- independent of
    Part C's own narrower slice-only behavior."""
    module = _build_module(run_host_match, ccpp_context)
    sites = list(iter_scheme_call_sites(module))
    assert len(sites) == 1
    if_op, call_op, scheme_name, phase, table_name = sites[0]
    assert scheme_name == "test_dbg_scheme"
    assert phase == "run"
    assert table_name == "test_dbg_scheme_run"


def test_device_arg_names_and_call_param_names_after_refactor(run_host_match, ccpp_context):
    module = _build_module(run_host_match, ccpp_context)
    ccpp_mod = find_ccpp_module(module.body.block.ops)
    bmdd = BuildMetaDataDescriptions()
    bmdd.traverse(ccpp_mod)
    meta_data = bmdd.meta_data

    _if_op, call_op, scheme_name, _phase, table_name = next(
        iter_scheme_call_sites(module)
    )

    device_names = _device_arg_names(scheme_name, table_name, meta_data)
    assert device_names == {"hosted"}

    param_names = _call_param_names(call_op, scheme_name, table_name, meta_data)
    assert param_names is not None
    assert len(_call_args(call_op)) == len(param_names)
    assert "hosted" in param_names
    assert "host_only" in param_names
