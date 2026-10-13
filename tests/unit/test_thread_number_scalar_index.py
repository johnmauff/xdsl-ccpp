"""Unit tests for `thread_number`/`number_of_threads` support
(`task11-omp-thread` item 3, Stage 2).

Real capgen-v1 treats `instance_number`/`number_of_instances` (already
implemented in this codebase) and `thread_number`/`number_of_threads` as two
symmetric entries in one general "registered scalar-index dimension"
mechanism (`CCPP_SCALAR_INDEX_DIMS`): a container DDT dimensioned by either
count standard name gets its scalar index auto-substituted at every scheme
call site that reaches into it. Stage 1 generalized the two previously
hardcoded choke points (`run_dispatch.py`'s DDT-array-indexing sibling-arg
search, `suite_cap.py`'s `active =` expression resolution) to consult that
table instead of hardcoding the instance pair; Stage 2 adds the thread pair
on top with no further changes to those two sites.

Unlike `instance_number`, `thread_number` has no `ccpp_suite_state`-style
framework state layered on top -- real capgen-v1's own generator never
reads `number_of_threads` for sizing anything (confirmed directly against
`generator/suite_cap.py`/`suite_data.py`: zero hits for either name, vs.
22+3 for the instance pair there). So there is no suite-state-indexing
test analogous to `test_multi_instance_suite_state.py`'s
`TestSuiteStateIsAPerInstanceAllocatableArray` here -- only the generic
substitution and per-phase signature-threading behavior.

Three things are tested:
  1. The DDT-member substitution itself (mirrors
     `test_run_dispatch_multi_instance_array_section.py`'s shape).
  2. `thread_number`/`number_of_threads` threaded through every lifecycle
     phase's own wrapper signature, not just `_run` (mirrors
     `test_multi_instance_suite_state.py`'s
     `TestLifecyclePhasesThreadInstanceThroughTheWrapper`) -- this is the
     load-bearing check that `lifecycle_cap.py`'s already-generic
     `extra_host_args` pre-scan really does pick up the new pair with zero
     code changes, not just an assumption from reading the code.
  3. Both pairs declared and exercised SIMULTANEOUSLY on one host, each
     with its own container DDT, confirming the table-driven lookup
     resolves each container by its own correct sibling index rather than
     cross-wiring them (the decisive proof this is genuinely general, not
     just "works for whichever pair happens to be first in the dict").
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.suite_cap import SuiteCAP


def _fortran_output(run_host_match, ccpp_context, scheme_metas, host_metas, suite_xml) -> str:
    module = run_host_match(
        scheme_metas=scheme_metas, host_metas=host_metas, suite_xml=suite_xml,
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


# ── 1. DDT-member substitution ──────────────────────────────────────────────

_THREAD_HOST_META = """\
[ccpp-table-properties]
  name = data
  type = host
[ccpp-arg-table]
  name = data
  type = host
[ col_start ]
  standard_name = horizontal_loop_begin
  units = count
  type = integer
  dimensions = ()
[ col_end ]
  standard_name = horizontal_loop_end
  units = count
  type = integer
  dimensions = ()
[ thread ]
  standard_name = thread_number
  units = index
  type = integer
  dimensions = ()
[ thread_data ]
  standard_name = thread_data
  units = ddt
  type = thread_type
  dimensions = (number_of_threads)
"""

_THREAD_DDT_META = """\
[ccpp-table-properties]
  name = thread_type
  type = ddt
[ccpp-arg-table]
  name = thread_type
  type = ddt
[ scratch_array ]
  standard_name = scratch_array
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
"""

_THREAD_SCHEME_META = f"""\
[ccpp-table-properties]
  name = thread_scheme
  type = scheme
[ccpp-arg-table]
  name = thread_scheme_run
  type = scheme
[ thread ]
  standard_name = thread_number
  units = index
  type = integer
  dimensions = ()
  intent = in
[ arr ]
  standard_name = scratch_array
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""


class TestThreadNumberDdtMemberSubstitution:
    def test_member_and_index_both_present_in_call(self, run_host_match, ccpp_context):
        """The container DDT's scratch_array member must print as
        thread_data(thread)%scratch_array(<slice>) inside ccpp_physics_run's
        own call to the suite -- mirrors the instance_number case exactly,
        proving the generalized CCPP_SCALAR_INDEX_DIMS lookup picks
        thread_number (not instance_number) for a number_of_threads-
        dimensioned container."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_THREAD_SCHEME_META], [_THREAD_HOST_META, _THREAD_DDT_META],
            minimal_suite_xml("thread_scheme"),
        )
        fn = _unwrapped(_fn_body(fortran, "ccpp_physics_run"))
        assert "thread_data(thread)%scratch_array(col_start:col_end)" in fn, (
            f"expected thread_data(thread)%scratch_array(...), got: {fn!r}"
        )


# ── 2. Threaded through every lifecycle phase's wrapper signature ──────────

_THREAD_LIFECYCLE_HOST_META = """\
[ccpp-table-properties]
  name = test_host
  type = host
[ccpp-arg-table]
  name = test_host
  type = host
[ thread ]
  standard_name = thread_number
  units = index
  type = integer
  dimensions = ()
[ nthreads ]
  standard_name = number_of_threads
  units = count
  type = integer
  dimensions = ()
"""

_THREAD_LIFECYCLE_SCHEME_META = f"""\
[ccpp-table-properties]
  name = unit_conv_scheme
  type = scheme
[ccpp-arg-table]
  name = unit_conv_scheme_run
  type = scheme
[ thread ]
  standard_name = thread_number
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


class TestLifecyclePhasesThreadThreadNumberThroughTheWrapper:
    """thread_number only declares itself on unit_conv_scheme's own _run
    entry point (matching the real instances_advection shape) -- so
    ccpp_register/ccpp_init/ccpp_final must get thread/nthreads from
    suite_cap.py's own unconditional per-phase synthesis
    (_synthesize_thread_number_arg/_synthesize_number_of_threads_arg) plus
    lifecycle_cap.py's already-generic extra_host_args pre-scan, not from
    any scheme's own non-_run metadata (there is none)."""

    def test_all_non_run_lifecycle_wrappers_accept_thread_and_nthreads(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_THREAD_LIFECYCLE_SCHEME_META], [_THREAD_LIFECYCLE_HOST_META],
            minimal_suite_xml("unit_conv_scheme"),
        )
        for fn_name in ("ccpp_register", "ccpp_init", "ccpp_final"):
            sig = _unwrapped(fortran.split(f"subroutine {fn_name}")[1].split("\n\n")[0])
            assert "thread" in sig, f"{fn_name}'s own signature missing 'thread': {sig!r}"
            assert "nthreads" in sig, f"{fn_name}'s own signature missing 'nthreads': {sig!r}"

    def test_run_call_passes_thread_through(self, run_host_match, ccpp_context):
        """unit_conv_scheme_run declares thread_number only on its own
        _run entry point -- confirm the suite-level _run wrapper
        (test_suite_physics, the function that actually calls the scheme)
        forwards the synthesized thread arg into that call by keyword."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_THREAD_LIFECYCLE_SCHEME_META], [_THREAD_LIFECYCLE_HOST_META],
            minimal_suite_xml("unit_conv_scheme"),
        )
        fn = _unwrapped(_fn_body(fortran, "test_suite_physics"))
        assert "thread=thread" in fn.replace(" ", "")


# ── 3. Both pairs declared and exercised simultaneously ─────────────────────

_BOTH_PAIRS_HOST_META = """\
[ccpp-table-properties]
  name = data
  type = host
[ccpp-arg-table]
  name = data
  type = host
[ col_start ]
  standard_name = horizontal_loop_begin
  units = count
  type = integer
  dimensions = ()
[ col_end ]
  standard_name = horizontal_loop_end
  units = count
  type = integer
  dimensions = ()
[ instance ]
  standard_name = instance_number
  units = index
  type = integer
  dimensions = ()
[ instance_data ]
  standard_name = instance_data
  units = ddt
  type = instance_type
  dimensions = (number_of_instances)
[ thread ]
  standard_name = thread_number
  units = index
  type = integer
  dimensions = ()
[ thread_data ]
  standard_name = thread_data
  units = ddt
  type = thread_type
  dimensions = (number_of_threads)
"""

_BOTH_PAIRS_DDT_META = """\
[ccpp-table-properties]
  name = instance_type
  type = ddt
[ccpp-arg-table]
  name = instance_type
  type = ddt
[ instance_array ]
  standard_name = instance_array
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)

[ccpp-table-properties]
  name = thread_type
  type = ddt
[ccpp-arg-table]
  name = thread_type
  type = ddt
[ thread_array ]
  standard_name = thread_array
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
"""

_INSTANCE_SCHEME_META = f"""\
[ccpp-table-properties]
  name = instance_scheme
  type = scheme
[ccpp-arg-table]
  name = instance_scheme_run
  type = scheme
[ instance ]
  standard_name = instance_number
  units = index
  type = integer
  dimensions = ()
  intent = in
[ arr ]
  standard_name = instance_array
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_THREAD_ONLY_SCHEME_META = f"""\
[ccpp-table-properties]
  name = thread_only_scheme
  type = scheme
[ccpp-arg-table]
  name = thread_only_scheme_run
  type = scheme
[ thread ]
  standard_name = thread_number
  units = index
  type = integer
  dimensions = ()
  intent = in
[ arr ]
  standard_name = thread_array
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_BOTH_PAIRS_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <scheme>instance_scheme</scheme>
    <scheme>thread_only_scheme</scheme>
  </group>
</suite>
"""


class TestInstanceAndThreadPairsResolveIndependently:
    def test_each_container_indexed_by_its_own_sibling_arg(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_INSTANCE_SCHEME_META, _THREAD_ONLY_SCHEME_META],
            [_BOTH_PAIRS_HOST_META, _BOTH_PAIRS_DDT_META],
            _BOTH_PAIRS_SUITE_XML,
        )
        fn = _unwrapped(_fn_body(fortran, "ccpp_physics_run"))
        assert "instance_data(instance)%instance_array(col_start:col_end)" in fn, (
            f"expected instance_data(instance)%instance_array(...), got: {fn!r}"
        )
        assert "thread_data(thread)%thread_array(col_start:col_end)" in fn, (
            f"expected thread_data(thread)%thread_array(...), got: {fn!r}"
        )
        # Regression guard: neither container's index should ever leak onto
        # the other's container name.
        assert "instance_data(thread)" not in fn
        assert "thread_data(instance)" not in fn
