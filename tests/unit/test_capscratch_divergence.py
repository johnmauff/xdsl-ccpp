"""Unit tests for CapScratch cap-var divergence: automatic update self/device
for a scheme that shares a device-resident cap-owned array (e.g.
lc_const_tend, backing const/const_tend or a constituent-tendency scratch
var like cld_liq_tend) but does not itself declare memory_space=device.

Real-world motivation: apply_constituent_tendencies_run shares lc_const_tend
with cld_liq_run (which is genuinely GPU-ported, with its own OpenACC
kernel), but apply_constituent_tendencies_run itself is plain, unannotated
Fortran. Before this fix, xdsl-ccpp had no way to express "this scheme is
not ported to GPU" for a CapScratch var -- it either lumped every touching
call into one blanket enter-once/exit-once residency treatment (a no-op for
already-persistently-resident arrays, since the blanket region's copyin
finds the array already present and its copyout never actually fires,
reference count never reaching zero) or required hand-written OpenACC in
the scheme's own source.

This mirrors the existing HostMatched present-vs-update divergence pattern
(see test_gpu_directives.py's TestGPUDivergedClauseRouting*,
cap_shared.find_diverged_suite_vars, gpu_data_pass.py's
_process_diverged_host_vars) but for CapScratch cap vars instead of
host-matched variables -- see cap_shared.find_diverged_capscratch_vars,
gpu_data_pass.py's _process_diverged_capscratch_vars.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.gpu_ccpp_cap_pass import GPUCcppCapPass
from xdsl_ccpp.transforms.gpu_data_pass import GPUDataPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP


def _fortran_output(run_host_match, ccpp_context, scheme_metas, host_metas, suite_xml) -> str:
    module = run_host_match(
        scheme_metas=scheme_metas,
        host_metas=host_metas,
        suite_xml=suite_xml,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    GPUDataPass(directive="acc").apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    GPUCcppCapPass(directive="acc").apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fn_body(fortran: str, fn_name: str) -> str:
    return fortran.split(f"subroutine {fn_name}")[1].split(f"end subroutine {fn_name}")[0]


_REGISTER_TABLE_LINES = """\
[ dyn_const ]
  standard_name = dynamic_constituents_for_{name}
  dimensions = (:)
  type = ccpp_constituent_properties_t
  intent = out
  allocatable = true
[ errmsg ]
  standard_name = ccpp_error_message
  long_name = Error message for error handling in CCPP
  units = none
  dimensions = ()
  type = character
  kind = len=512
  intent = out
[ errflg ]
  standard_name = ccpp_error_code
  long_name = Error flag for error handling in CCPP
  units = 1
  dimensions = ()
  type = integer
  intent = out
"""


# ── direct framework-mapped path: producer declares device, consumer doesn't ─

_DIRECT_PRODUCER_SCHEME = f"""\
[ccpp-table-properties]
  name = test_csdiv_producer_scheme
  type = scheme
[ccpp-arg-table]
  name = test_csdiv_producer_scheme_register
  type = scheme
{_REGISTER_TABLE_LINES.format(name="test_csdiv_producer")}
[ccpp-arg-table]
  name = test_csdiv_producer_scheme_run
  type = scheme
[ const_tend ]
  standard_name = ccpp_constituent_tendencies
  units = none
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension, number_of_ccpp_constituents)
  intent = inout
  memory_space = device
{CCPP_MANDATORY_ARGS}
"""

_DIRECT_CONSUMER_SCHEME = f"""\
[ccpp-table-properties]
  name = test_csdiv_consumer_scheme
  type = scheme
[ccpp-arg-table]
  name = test_csdiv_consumer_scheme_run
  type = scheme
[ const_tend ]
  standard_name = ccpp_constituent_tendencies
  units = none
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension, number_of_ccpp_constituents)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_DIRECT_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_csdiv_direct_suite" version="1.0">
  <group name="physics">
    <scheme>test_csdiv_producer_scheme</scheme>
    <scheme>test_csdiv_consumer_scheme</scheme>
  </group>
</suite>
"""


class TestDirectFrameworkMappedDivergence:
    def test_consumer_gets_update_self_device_not_blanket_copyin(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_DIRECT_PRODUCER_SCHEME, _DIRECT_CONSUMER_SCHEME], [], _DIRECT_SUITE_XML,
        )
        suite_fn = _fn_body(fortran, "test_csdiv_direct_suite_suite_physics")

        assert "present(const_tend" in suite_fn
        assert "update self(const_tend" in suite_fn
        assert "update device(const_tend" in suite_fn
        # Not lumped into the blanket enter-once/exit-once region -- that
        # would be a no-op for an already-persistently-resident array (the
        # actual bug this feature fixes).
        assert "copyin(const_tend" not in suite_fn


# ── constituent-tendency scratch-var path: producer uses an alias, ─────────
# ── consumer uses the direct reference -- ref resolution must prefer the ───
# ── direct (full-array) reference, not the producer's narrower slice. ──────

_TEND_PRODUCER_SCHEME = f"""\
[ccpp-table-properties]
  name = test_csdiv_tend_producer_scheme
  type = scheme
[ccpp-arg-table]
  name = test_csdiv_tend_producer_scheme_register
  type = scheme
{_REGISTER_TABLE_LINES.format(name="test_csdiv_tend_producer")}
[ccpp-arg-table]
  name = test_csdiv_tend_producer_scheme_run
  type = scheme
[ my_tend ]
  standard_name = tendency_of_test_csdiv_tend_quantity
  units = kg kg-1 s-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
  constituent = True
  memory_space = device
{CCPP_MANDATORY_ARGS}
"""

_TEND_CONSUMER_SCHEME = f"""\
[ccpp-table-properties]
  name = test_csdiv_tend_consumer_scheme
  type = scheme
[ccpp-arg-table]
  name = test_csdiv_tend_consumer_scheme_run
  type = scheme
[ const_tend ]
  standard_name = ccpp_constituent_tendencies
  units = none
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension, number_of_ccpp_constituents)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_TEND_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_csdiv_tend_suite" version="1.0">
  <group name="physics">
    <scheme>test_csdiv_tend_producer_scheme</scheme>
    <scheme>test_csdiv_tend_consumer_scheme</scheme>
  </group>
</suite>
"""


class TestConstituentTendencyScratchVarDivergence:
    def test_ref_prefers_direct_reference_over_producer_alias(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_TEND_PRODUCER_SCHEME, _TEND_CONSUMER_SCHEME], [], _TEND_SUITE_XML,
        )
        suite_fn = _fn_body(fortran, "test_csdiv_tend_suite_suite_physics")

        # One canonical reference is used throughout for this cap var --
        # both the present() wrap around the producer's call and the
        # update self/device around the consumer's -- and it must be
        # const_tend (the whole shared array the consumer actually reads/
        # writes), not my_tend (a pointer slice covering only this one
        # constituent): syncing just the slice would silently drop every
        # other constituent's data, and present()-checking only the slice
        # would be a weaker assertion than checking the whole array.
        assert "present(const_tend" in suite_fn
        assert "update self(const_tend" in suite_fn
        assert "update device(const_tend" in suite_fn
        assert "present(my_tend" not in suite_fn
        assert "update self(my_tend" not in suite_fn
        assert "update device(my_tend" not in suite_fn


# ── regression: both schemes agree (no divergence) keeps blanket treatment ──

_AGREE_PRODUCER_SCHEME = f"""\
[ccpp-table-properties]
  name = test_csdiv_agree_producer_scheme
  type = scheme
[ccpp-arg-table]
  name = test_csdiv_agree_producer_scheme_register
  type = scheme
{_REGISTER_TABLE_LINES.format(name="test_csdiv_agree_producer")}
[ccpp-arg-table]
  name = test_csdiv_agree_producer_scheme_run
  type = scheme
[ const_tend ]
  standard_name = ccpp_constituent_tendencies
  units = none
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension, number_of_ccpp_constituents)
  intent = inout
  memory_space = device
{CCPP_MANDATORY_ARGS}
"""

_AGREE_CONSUMER_SCHEME = f"""\
[ccpp-table-properties]
  name = test_csdiv_agree_consumer_scheme
  type = scheme
[ccpp-arg-table]
  name = test_csdiv_agree_consumer_scheme_run
  type = scheme
[ const_tend ]
  standard_name = ccpp_constituent_tendencies
  units = none
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension, number_of_ccpp_constituents)
  intent = inout
  memory_space = device
{CCPP_MANDATORY_ARGS}
"""

_AGREE_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_csdiv_agree_suite" version="1.0">
  <group name="physics">
    <scheme>test_csdiv_agree_producer_scheme</scheme>
    <scheme>test_csdiv_agree_consumer_scheme</scheme>
  </group>
</suite>
"""


class TestNonDivergedRegression:
    def test_both_schemes_agreeing_on_device_keeps_blanket_treatment(
        self, run_host_match, ccpp_context
    ):
        """No divergence (both schemes declare memory_space=device) means
        this cap var is untouched by the new per-call routing -- it keeps
        its existing, unchanged blanket enter-once/exit-once treatment."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_AGREE_PRODUCER_SCHEME, _AGREE_CONSUMER_SCHEME], [], _AGREE_SUITE_XML,
        )
        suite_fn = _fn_body(fortran, "test_csdiv_agree_suite_suite_physics")

        assert "copyin(const_tend" in suite_fn
        assert "update self(const_tend" not in suite_fn
        assert "update device(const_tend" not in suite_fn
