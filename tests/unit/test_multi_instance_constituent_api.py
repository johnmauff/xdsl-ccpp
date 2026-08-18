"""Regression test for a real gap found while re-investigating
examples/instances_advection once examples/instances went CI-green
(ccpp_cap_refactor_plan.md's "instances/instances_advection" backlog entry,
task #35).

The originally-tracked memref.copy verifier crash for instances_advection
turned out to already be fixed (an incidental side effect of the
multi-instance migration, PR #76) -- but re-testing it exposed a much
bigger, previously-invisible gap once that crash was out of the way:
constituent_cap.py (register_constituents/deallocate_dynamic_constituents/
initialize_constituents/const_get_index/number_constituents/
constituents_array/is_scheme_constituent/model_const_properties) had ZERO
instance-awareness -- every one of these operated on a single shared set of
module-level arrays (lc_all_constituents, lc_constituent_array,
lc_const_tend, lc_const_props, plus any scheme-scratch var), with no way to
know which model instance a given call was for, even though
examples/instances_advection's own main.F90 calls every one of them with
instance=/ninstances=.

Fixed by introducing a new per-instance bundle derived type
(<camel_name>_lc_instance_t) collecting every constituent-API-owned array
into one allocatable lc_instances(:) array -- the same "array-of-DDT-
instance" idiom examples/instances' own host-declared instance_data
already establishes for this codebase, just cap-owned/generated here
instead of host-declared -- lazily allocated + sized by number_of_instances
inside register_constituents only (the entry point the driver always calls
first, with ninstances); every constituent-API subroutine gained an
`instance` dummy argument. cap_shared.py's FRAMEWORK_STD_NAME_TO_CAP_VAR
resolution (consumed by run_dispatch.py for a scheme's own ccpp_constituents/
ccpp_constituent_tendencies args) also needed to index by instance, fixed at
its single build site in ccpp_cap.py's _build_cap_var_map.

Gated on the host declaring instance_number at all -- a non-multi-instance
host (every other constituent-using example: advection, constituents_dim,
capgen, ddthost) must keep its original flat-module-var output
byte-identical; confirmed via the full existing test suite, 0 regressions.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

_HOST_META = """\
[ccpp-table-properties]
  name = test_host
  type = host
[ccpp-arg-table]
  name = test_host
  type = host
[ instance ]
  standard_name = instance_number
  units = index
  type = integer
  dimensions = ()
[ ninstances ]
  standard_name = number_of_instances
  units = count
  type = integer
  dimensions = ()
"""

_SCHEME_META = f"""\
[ccpp-table-properties]
  name = cld_liq
  type = scheme
[ccpp-arg-table]
  name = cld_liq_register
  type = scheme
[ dyn_const ]
  standard_name = dynamic_constituents_for_cld_liq
  dimensions = (:)
  type = ccpp_constituent_properties_t
  intent = out
  allocatable = true
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = cld_liq_run
  type = scheme
[ instance ]
  standard_name = instance_number
  units = index
  type = integer
  dimensions = ()
  intent = in
[ cld_liq_array ]
  standard_name = cloud_liquid_dry_mixing_ratio
  advected = .true.
  units = kg kg-1
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  type = real
  kind = kind_phys
  intent = inout
[ cld_liq_tend ]
  standard_name = tendency_of_cloud_liquid_dry_mixing_ratio
  units = kg kg-1 s-1
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  type = real
  kind = kind_phys
  intent = out
  constituent = True
[ all_consts ]
  standard_name = ccpp_constituents
  units = kg kg-1
  dimensions = (horizontal_dimension, vertical_layer_dimension, number_of_ccpp_constituents)
  type = real
  kind = kind_phys
  intent = in
[ all_tends ]
  standard_name = ccpp_constituent_tendencies
  units = kg kg-1 s-1
  dimensions = (horizontal_dimension, vertical_layer_dimension, number_of_ccpp_constituents)
  type = real
  kind = kind_phys
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <scheme>cld_liq</scheme>
  </group>
</suite>
"""


def _fortran_output(
    run_host_match, ccpp_context, host_meta: str = _HOST_META, scheme_meta: str = _SCHEME_META
) -> str:
    module = run_host_match(
        scheme_metas=[scheme_meta],
        host_metas=[host_meta],
        suite_xml=_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fn_body(fortran: str, fn_name: str) -> str:
    return fortran.split(f"subroutine {fn_name}")[1].split(f"end subroutine {fn_name}")[0]


def _unwrapped(fortran_fragment: str) -> str:
    """Collapse Fortran line-continuation ('&' + newline + indent) so a
    declaration/call spanning multiple printed lines can be matched as one
    string."""
    return " ".join(
        line.rstrip().rstrip("&").strip() for line in fortran_fragment.splitlines()
    )


class TestConstituentApiHasAPerInstanceBundleType:
    def test_bundle_type_declared_before_the_array_that_uses_it(
        self, run_host_match, ccpp_context
    ):
        """Fortran requires a derived-type definition to appear before any
        variable declared with it in the same specification part -- the
        exact bug found while implementing this: printing lc_instances(:)
        before its own type definition produced 'has no IMPLICIT type'."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        assert "type :: Test_lc_instance_t" in fortran
        assert "type(Test_lc_instance_t), target, allocatable :: lc_instances(:)" in fortran
        type_def_pos = fortran.index("type :: Test_lc_instance_t")
        var_decl_pos = fortran.index("type(Test_lc_instance_t), target, allocatable :: lc_instances(:)")
        assert type_def_pos < var_decl_pos

    def test_no_plain_module_scalar_survives(self, run_host_match, ccpp_context):
        """The old flat module var declaration (lc_all_constituents as its
        own bare module-scope variable, printed via the CCPPModuleVarOp
        preamble loop with a 2-space indent) must not survive once the
        host is multi-instance -- only the bundle-type COMPONENT form
        (4-space indent, inside `type :: ... end type`) should. The
        component must NOT carry `target` -- Fortran forbids TARGET on a
        derived-type component; only the containing lc_instances(:)
        variable (checked above) carries it, and that propagates to every
        subobject including this one."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        assert "\n  type(ccpp_constituent_properties_t), allocatable, target :: lc_all_constituents(:)\n" \
            not in fortran
        assert "\n    type(ccpp_constituent_properties_t), allocatable :: lc_all_constituents(:)\n" \
            in fortran
        assert "lc_instances(instance)%lc_all_constituents" in fortran


class TestConstituentApiSubroutinesAreInstanceAware:
    def test_register_constituents_lazily_allocates_sized_by_ninstances(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(run_host_match, ccpp_context)
        body = _unwrapped(_fn_body(fortran, "Test_ccpp_register_constituents"))
        assert "instance" in _unwrapped(
            fortran.split("subroutine Test_ccpp_register_constituents(")[1].split(")")[0]
        )
        assert "if (.not. allocated(lc_instances)) then allocate(lc_instances(ninstances))" in body
        assert "lc_instances(instance)%lc_all_constituents" in body

    def test_every_constituent_subroutine_gains_instance_arg(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context)
        for fn_name, kind in (
            ("Test_ccpp_is_scheme_constituent", "subroutine"),
            ("Test_ccpp_deallocate_dynamic_constituents", "subroutine"),
            ("Test_ccpp_number_constituents", "subroutine"),
            ("Test_ccpp_initialize_constituents", "subroutine"),
            ("Test_constituents_array", "function"),
            ("Test_const_get_index", "subroutine"),
            ("Test_model_const_properties", "function"),
        ):
            sig = _unwrapped(
                fortran.split(f"{kind} {fn_name}(")[1].split(")")[0]
            )
            assert "instance" in sig, f"{fn_name} missing instance: {sig!r}"

    def test_non_register_subroutines_guard_on_lc_instances_allocated(
        self, run_host_match, ccpp_context
    ):
        """initialize_constituents/const_get_index must not index
        lc_instances(instance) before confirming lc_instances itself is
        allocated -- indexing an unallocated array is illegal Fortran, not
        merely an unallocated-component check."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        for fn_name in ("Test_ccpp_initialize_constituents", "Test_const_get_index"):
            body = _unwrapped(_fn_body(fortran, fn_name))
            assert "if (.not. allocated(lc_instances)) then" in body


class TestFrameworkConstituentArraysAreIndexedByInstanceInRunDispatch:
    def test_ccpp_constituents_and_tendencies_resolve_through_lc_instances(
        self, run_host_match, ccpp_context
    ):
        """A scheme's own ccpp_constituents/ccpp_constituent_tendencies args
        (FRAMEWORK_STD_NAME_TO_CAP_VAR, resolved once in ccpp_cap.py's
        _build_cap_var_map) must resolve to lc_instances(instance)%..., not
        the old bare module-var name, inside the physics_run dispatch."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        run_body = _unwrapped(_fn_body(fortran, "ccpp_physics_run"))
        assert "lc_instances(instance)%lc_constituent_array" in run_body
        assert "lc_instances(instance)%lc_const_tend" in run_body

    def test_constituent_tendency_scratch_var_resolves_through_lc_instances(
        self, run_host_match, ccpp_context
    ):
        """cld_liq_tend (constituent=True, a pointer slice into
        lc_const_tend) must resolve to lc_instances(instance)%lc_cld_liq_tend,
        matching the scratch-var branch of the same fix."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        run_body = _unwrapped(_fn_body(fortran, "ccpp_physics_run"))
        assert "lc_instances(instance)%lc_cld_liq_tend" in run_body


class TestSchemeLevelDynamicRegistrationOutputIsInstanceAware:
    """Regression test for a real gfortran CI build failure found AFTER the
    fix above first landed: cld_liq_register's own dyn_const output
    (allocatable ccpp_constituent_properties_t, a scheme's own
    dynamically-registered constituent list) is passed into the suite call
    from ccpp_register via lifecycle_cap.py's own dedicated CapVarRefOp
    branch for this exact arg shape -- keyed purely by matching
    constituent_cap.py's bare naming convention (lc_<bare>). Once
    constituent_cap.py moved that same array into the per-instance bundle
    (lc_instances(instance)%lc_dyn_const), this branch kept emitting the
    bare, now-nonexistent lc_dyn_const -- confirmed in real CI:
    "Symbol 'lc_dyn_const' at (1) has no IMPLICIT type".

    Not exercised by the other tests in this file: their own _SCHEME_META
    has no _register table at all, only fixed_advected (`advected=.true.`)
    -- this class is the only one that actually declares a scheme-level
    dynamic registration output.
    """

    def test_ccpp_register_passes_the_per_instance_component(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(run_host_match, ccpp_context)
        body = _unwrapped(_fn_body(fortran, "ccpp_register"))
        assert "test_suite_suite_register(lc_instances(instance)%lc_dyn_const" in body
        assert "test_suite_suite_register(lc_dyn_const" not in body

    def test_ccpp_register_allocates_lc_instances_before_referencing_it(
        self, run_host_match, ccpp_context
    ):
        """Regression test for a real gfortran CI SEGFAULT found after the
        fix above first landed: lc_instances(instance)%lc_dyn_const is
        indexed straight into an OUTER array (lc_instances) that nothing
        has allocated yet -- ccpp_register is the driver's own first
        lifecycle call, running BEFORE register_constituents (where
        lc_instances is normally lazily allocated) ever gets a chance to.
        Must allocate lc_instances itself, guarded, before the call that
        references it."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        body = _unwrapped(_fn_body(fortran, "ccpp_register"))
        alloc_pos = body.index("if (.not. allocated(lc_instances)) then allocate(lc_instances(ninstances))")
        call_pos = body.index("test_suite_suite_register(lc_instances(instance)%lc_dyn_const")
        assert alloc_pos < call_pos


# Host declares only ONE of the two paired standard names -- confirmed real
# by Copilot review on PR #77: instance_local_name/ninstances_local_name are
# not two independent optionals, they're a single paired contract every
# downstream consumer (cap_var_map's lc_instances(instance)% wrapping,
# constituent_cap.py's bundle/allocation, lifecycle_cap.py's LazyAllocOp
# guard) assumes holds. Before the fix, a host declaring only
# instance_number (or only number_of_instances) would incorrectly enable
# multi-instance wrapping with no matching allocation/signature support --
# e.g. a literal "None" spliced into allocate(lc_instances(None)).
_HOST_META_INSTANCE_ONLY = """\
[ccpp-table-properties]
  name = test_host
  type = host
[ccpp-arg-table]
  name = test_host
  type = host
[ instance ]
  standard_name = instance_number
  units = index
  type = integer
  dimensions = ()
"""

_HOST_META_NINSTANCES_ONLY = """\
[ccpp-table-properties]
  name = test_host
  type = host
[ccpp-arg-table]
  name = test_host
  type = host
[ ninstances ]
  standard_name = number_of_instances
  units = count
  type = integer
  dimensions = ()
"""

# _SCHEME_META's own cld_liq_run unconditionally declares an `instance`
# arg (standard_name=instance_number) that HostVariableMatchPass requires
# to resolve to *some* host var regardless of the instance/ninstances
# pairing logic under test here -- unrelated to this bug, but it means
# _SCHEME_META can't be reused as-is against a host that omits
# instance_number entirely (_HOST_META_NINSTANCES_ONLY). This variant
# drops that one arg so the ninstances-alone direction is actually
# testable; everything else is identical to _SCHEME_META.
_SCHEME_META_NO_INSTANCE_ARG = _SCHEME_META.replace(
    """\
[ instance ]
  standard_name = instance_number
  units = index
  type = integer
  dimensions = ()
  intent = in
""",
    "",
)


class TestPartialMultiInstanceMetadataStaysSingleInstance:
    """Regression test for a real correctness bug found by Copilot review
    on PR #77: multi-instance mode was being gated on instance_local_name
    alone, without checking ninstances_local_name was also present."""

    def test_instance_number_alone_does_not_enable_multi_instance(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(run_host_match, ccpp_context, host_meta=_HOST_META_INSTANCE_ONLY)
        assert "lc_instances" not in fortran
        assert "None" not in fortran
        # Falls back to the plain, non-multi-instance constituent API shape.
        assert "type(ccpp_constituent_properties_t), target, allocatable :: lc_all_constituents(:)" \
            in fortran

    def test_instance_number_alone_does_not_index_ccpp_suite_state(
        self, run_host_match, ccpp_context
    ):
        """Regression test for a second, suite_cap.py-own instance of the
        same paired-contract bug, found while probing the fix above: with
        only instance_number declared, _build_state_globals correctly
        falls back to a plain scalar ccpp_suite_state -- but
        _generate_lifecycle_fn's own instance_local_name/
        ninstances_local_name resolution (fed by a SCHEME's own explicit
        instance_number arg, not just suite_cap.py's synthesis) still
        indexed it as ccpp_suite_state(instance), which is invalid Fortran
        against a scalar."""
        fortran = _fortran_output(run_host_match, ccpp_context, host_meta=_HOST_META_INSTANCE_ONLY)
        assert "character(len=16) :: ccpp_suite_state = 'uninitialized'" in fortran
        assert "ccpp_suite_state(" not in fortran

    def test_number_of_instances_alone_does_not_enable_multi_instance(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(
            run_host_match,
            ccpp_context,
            host_meta=_HOST_META_NINSTANCES_ONLY,
            scheme_meta=_SCHEME_META_NO_INSTANCE_ARG,
        )
        assert "lc_instances" not in fortran
        assert "None" not in fortran
        assert "type(ccpp_constituent_properties_t), target, allocatable :: lc_all_constituents(:)" \
            in fortran
