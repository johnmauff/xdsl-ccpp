"""Regression test for a real ctest failure found while wiring
examples/instances into the real CMake/CI build (ccpp_cap_refactor_plan.md's
"instances/instances_advection" backlog entry, post-Stage-5 fix):

    An error occurred in ccpp_init:
    Invalid initial CCPP state, 'initialized' in unit_conv_suite_initialize
    instance: 2

Root cause: ccpp_suite_state was a single module-scope SCALAR shared by
every model instance, so registering/initializing instance 2 saw instance
1's own already-'initialized' state and errored -- real capgen-v1 gives
each instance its own entry in an array sized by number_of_instances.

Fixed by:
  - suite_cap.py's generateStateCheckOps/generateStateAssignment tagging
    their ccpp_suite_state AddressOfOp with the calling subroutine's own
    instance_number-standard-name dummy arg (ccpp_instance_ref), so
    print_ftn.py prints ccpp_suite_state(instance) instead of the bare
    shared name.
  - _build_state_globals declaring ccpp_suite_state allocatable/deferred-
    shape (number_of_instances is a genuine runtime HOST scalar, never a
    compile-time constant) and _build_suite_state_lazy_alloc allocating +
    initializing it on first use, sized by number_of_instances.
  - _synthesize_instance_number_arg/_synthesize_number_of_instances_arg
    threading instance/number_of_instances through every lifecycle phase
    (register/init/finalize/timestep_init/timestep_final), matching real
    capgen-v1 exactly, even though no scheme's own entry point for those
    phases declares either one.
  - lifecycle_cap.py's own dispatcher-wrapper pre-scan (ccpp_register/
    ccpp_init/ccpp_final/ccpp_physics_timestep_init/
    ccpp_physics_timestep_final) extended with a name-based HOST-table
    fallback (mirroring run_dispatch.py's own, already-generic mechanism
    for the _run/ccpp_physics_run side) so these two framework-synthesized
    args -- absent from every scheme's own non-_run metadata -- still get
    exposed as real passthrough dummy arguments on the wrapper instead of
    silently falling back to a fresh, always-zero local alloca.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
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
  name = unit_conv_scheme
  type = scheme
[ccpp-arg-table]
  name = unit_conv_scheme_run
  type = scheme
[ instance ]
  standard_name = instance_number
  units = index
  type = integer
  dimensions = ()
  intent = in
[ arr ]
  standard_name = data_array
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""


def _fortran_output(run_host_match, ccpp_context) -> str:
    module = run_host_match(
        scheme_metas=[_SCHEME_META],
        host_metas=[_HOST_META],
        suite_xml=minimal_suite_xml("unit_conv_scheme"),
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


class TestSuiteStateIsAPerInstanceAllocatableArray:
    def test_declared_allocatable_not_a_fixed_scalar(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context)
        assert "allocatable, dimension(:) :: ccpp_suite_state" in fortran
        assert "character(len=16) :: ccpp_suite_state = " not in fortran

    def test_lazily_allocated_and_sized_by_number_of_instances(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(run_host_match, ccpp_context)
        assert "if (.not. allocated(ccpp_suite_state)) then" in fortran
        assert "allocate(ccpp_suite_state(ninstances))" in fortran

    def test_check_and_assignment_are_indexed_by_instance(self, run_host_match, ccpp_context):
        """Each lifecycle subroutine must check/assign its OWN instance's
        entry (ccpp_suite_state(instance)), never the bare shared name --
        the exact bug the real ctest failure exposed."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        init_body = _unwrapped(
            _fn_body(fortran, "test_suite_suite_initialize")
        )
        assert "ccpp_suite_state(instance)" in init_body
        assert "ccpp_suite_state)" not in init_body.replace(
            "ccpp_suite_state(instance)", ""
        ).replace("allocated(ccpp_suite_state)", "")


class TestLifecyclePhasesThreadInstanceThroughTheWrapper:
    def test_register_wrapper_forwards_instance_args_not_a_local_alloca(
        self, run_host_match, ccpp_context
    ):
        """ccpp_register's own scheme metadata never declares
        instance_number/number_of_instances (only _run does) -- confirm the
        wrapper still exposes them as real passthrough dummy args, not a
        fresh always-zero local (the bug: a missing/incomplete pre-scan
        would silently pass 0 for every instance)."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        sig = _unwrapped(_fn_body(fortran, "ccpp_register").split("\n\n")[0])
        assert "instance" in sig and "ninstances" in sig
        call = _unwrapped(_fn_body(fortran, "ccpp_register"))
        assert "test_suite_suite_register(instance, ninstances" in call

    def test_all_non_run_lifecycle_wrappers_accept_instance_and_ninstances(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(run_host_match, ccpp_context)
        for fn_name in (
            "ccpp_register", "ccpp_init", "ccpp_final",
            "ccpp_physics_timestep_init", "ccpp_physics_timestep_final",
        ):
            sig = _unwrapped(fortran.split(f"subroutine {fn_name}(")[1].split(")")[0])
            assert "instance" in sig, f"{fn_name} missing instance: {sig!r}"
            assert "ninstances" in sig, f"{fn_name} missing ninstances: {sig!r}"
