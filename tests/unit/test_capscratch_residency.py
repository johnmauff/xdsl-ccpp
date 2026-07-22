"""Unit tests for CapScratch GPU residency.

CapScratch args (pure framework-owned scratch memory: no host variable
match, not SuiteOwned) have no residency story at all before this fix --
memory_space=device on such an arg is read nowhere in ccpp_cap.py or
constituent_cap.py. This is the third and last residency gap (after
SuiteOwned's LazyAllocOp and HostMatched's present/update residency),
covering the shared cap-module-scope arrays constituent-tendency scratch
vars (e.g. cld_liq_tend) resolve into -- lc_constituent_array/lc_const_tend
-- established via #ifdef USE_GPU / !$acc enter data create(...) directly
after each array's allocate() in ccpp_initialize_constituents, and torn
down via !$acc exit data delete(...) in ccpp_physics_finalize (mirroring
suite_cap.py's _inject_suite_owned_gpu_exit exactly, but unconditional
since these arrays are cap-module-global, not suite-scoped).
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
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


_UNRELATED_HOST = """\
[ccpp-table-properties]
  name = test_capscratch_host
  type = module
[ccpp-arg-table]
  name = test_capscratch_host
  type = module
[ dummy_host_var ]
  standard_name = test_capscratch_unrelated_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
"""


# ── Constituent-tendency scratch var (cld_liq_tend-style pointer slice) ──────

_TEND_SCHEME = f"""\
[ccpp-table-properties]
  name = test_capscratch_tend_scheme
  type = scheme
[ccpp-arg-table]
  name = test_capscratch_tend_scheme_run
  type = scheme
[ tend ]
  standard_name = tendency_of_test_capscratch_quantity
  units = kg kg-1 s-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
  constituent = True
  memory_space = device
{CCPP_MANDATORY_ARGS}
"""

_TEND_SUITE_XML = minimal_suite_xml(
    "test_capscratch_tend_scheme", suite_name="test_capscratch_tend_suite"
)


class TestConstituentTendencyScratchResidency:
    def test_lc_const_tend_gets_enter_and_exit_data(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_TEND_SCHEME], [_UNRELATED_HOST], _TEND_SUITE_XML,
        )
        init_fn = _fn_body(fortran, "TestCapscratchTend_ccpp_initialize_constituents")
        finalize_fn = _fn_body(fortran, "TestCapscratchTend_ccpp_physics_finalize")

        assert "enter data create(lc_const_tend)" in init_fn
        assert "exit data delete(lc_const_tend)" in finalize_fn
        # The pointer slice itself is never separately made resident --
        # OpenACC tracks residency by lc_const_tend's actual memory, not
        # the pointer name used to reference a slice of it.
        assert "lc_test_capscratch_quantity" not in init_fn or "create(lc_test_capscratch_quantity" not in init_fn


# ── Direct framework-mapped path (apply_constituent_tendencies-style) ───────

_FRAMEWORK_SCHEME_TEMPLATE = """\
[ccpp-table-properties]
  name = test_capscratch_framework_scheme
  type = scheme
[ccpp-arg-table]
  name = test_capscratch_framework_scheme_register
  type = scheme
[ dyn_const ]
  standard_name = dynamic_constituents_for_test_capscratch_framework
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
[ccpp-arg-table]
  name = test_capscratch_framework_scheme_run
  type = scheme
[ const ]
  standard_name = ccpp_constituents
  units = none
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension, number_of_ccpp_constituents)
  intent = inout
{const_residency}
[ const_tend ]
  standard_name = ccpp_constituent_tendencies
  units = none
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension, number_of_ccpp_constituents)
  intent = inout
""" + CCPP_MANDATORY_ARGS

_FRAMEWORK_SUITE_XML = minimal_suite_xml(
    "test_capscratch_framework_scheme", suite_name="test_capscratch_framework_suite"
)


class TestFrameworkMappedResidency:
    def test_const_residency_activates_only_constituent_array_independently(
        self, run_host_match, ccpp_context
    ):
        """memory_space=device on `const` only (not `const_tend`) must
        activate lc_constituent_array's residency without also activating
        lc_const_tend's -- the two shared arrays are tracked independently,
        since a suite might reasonably want one device-resident but not the
        other."""
        scheme = _FRAMEWORK_SCHEME_TEMPLATE.format(const_residency="  memory_space = device")
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [scheme], [_UNRELATED_HOST], _FRAMEWORK_SUITE_XML,
        )
        init_fn = _fn_body(fortran, "TestCapscratchFramework_ccpp_initialize_constituents")
        finalize_fn = _fn_body(fortran, "TestCapscratchFramework_ccpp_physics_finalize")

        assert "enter data create(lc_constituent_array)" in init_fn
        assert "enter data create(lc_const_tend)" not in init_fn
        assert "exit data delete(lc_constituent_array)" in finalize_fn
        assert "exit data delete(lc_const_tend)" not in finalize_fn

    def test_no_memory_space_leaves_both_arrays_unaffected(self, run_host_match, ccpp_context):
        """Regression guard: no memory_space anywhere means CapScratch
        residency is a complete no-op -- matching every example's current
        (pre-this-feature) output exactly."""
        scheme = _FRAMEWORK_SCHEME_TEMPLATE.format(const_residency="")
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [scheme], [_UNRELATED_HOST], _FRAMEWORK_SUITE_XML,
        )
        init_fn = _fn_body(fortran, "TestCapscratchFramework_ccpp_initialize_constituents")
        finalize_fn = _fn_body(fortran, "TestCapscratchFramework_ccpp_physics_finalize")

        assert "USE_GPU" not in init_fn
        assert "enter data" not in init_fn
        assert "USE_GPU" not in finalize_fn
        assert "exit data" not in finalize_fn


# ── OR-across-occurrences: same std_name, two different groups ─────────────

_OR_SCHEME_A = f"""\
[ccpp-table-properties]
  name = test_capscratch_or_scheme_a
  type = scheme
[ccpp-arg-table]
  name = test_capscratch_or_scheme_a_run
  type = scheme
[ tend_a ]
  standard_name = tendency_of_test_capscratch_or_quantity
  units = kg kg-1 s-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
  constituent = True
{CCPP_MANDATORY_ARGS}
"""

_OR_SCHEME_B = f"""\
[ccpp-table-properties]
  name = test_capscratch_or_scheme_b
  type = scheme
[ccpp-arg-table]
  name = test_capscratch_or_scheme_b_run
  type = scheme
[ tend_b ]
  standard_name = tendency_of_test_capscratch_or_quantity
  units = kg kg-1 s-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
  constituent = True
  memory_space = device
{CCPP_MANDATORY_ARGS}
"""

_OR_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_capscratch_or_suite" version="1.0">
  <group name="group1">
    <scheme>test_capscratch_or_scheme_a</scheme>
  </group>
  <group name="group2">
    <scheme>test_capscratch_or_scheme_b</scheme>
  </group>
</suite>
"""


class TestOrAcrossOccurrencesResidency:
    def test_second_group_declaring_memory_space_still_activates_shared_array(
        self, run_host_match, ccpp_context
    ):
        """Two groups both feed a constituent-tendency scratch var resolving
        to the same standard_name (and therefore the same shared
        lc_const_tend array) -- only the SECOND group's occurrence declares
        memory_space=device. Before the OR-across-occurrences fix, the
        first-occurrence-wins dedup gate would silently discard this later
        occurrence's residency request entirely."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_OR_SCHEME_A, _OR_SCHEME_B], [_UNRELATED_HOST], _OR_SUITE_XML,
        )
        init_fn = _fn_body(fortran, "TestCapscratchOr_ccpp_initialize_constituents")
        finalize_fn = _fn_body(fortran, "TestCapscratchOr_ccpp_physics_finalize")

        assert "enter data create(lc_const_tend)" in init_fn
        assert "exit data delete(lc_const_tend)" in finalize_fn
