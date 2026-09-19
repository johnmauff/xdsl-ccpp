"""Unit tests for SuiteOwned GPU residency.

SuiteOwned scheme args (advected/allocatable arrays, e.g. examples/
advection_flat_host's cld_liq_array) are allocated as module-scope arrays
inside the generated <suite>_suite_cap module (suite_cap.py/
suite_variable_model.py) -- a structurally different allocation path from
CapScratch's cap_var_map in ccpp_cap.py, and from HostMatched args' present/
update handling in gpu_ccpp_cap_pass.py/gpu_data_pass.py. Before this fix,
memory_space=device on a SuiteOwned arg's declaration was silently ignored --
confirmed as a real bug via a runtime "PRESENT clause was not found on
device" error on actual GPU hardware for examples/advection_flat_host's
cld_liq_array.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

import pytest

pytestmark = pytest.mark.usefixtures("legacy_mode")

# ── fixtures ────────────────────────────────────────────────────────────────
#
# A host module declaring ncols/pver (horizontal_dimension/
# vertical_layer_dimension) -- needed so the SuiteOwned array's allocation
# dimensions actually resolve in _register/_init (mirroring
# examples/advection_flat_host's flat_host_mod.meta pattern). Without a host
# declaration for these, dim_var_refs would stay empty and no LazyAllocOp
# would ever be emitted at all -- exactly the latent (and unrelated,
# pre-existing) case this work found in examples/helloworld's temp_layer
# (whose alloc dims use horizontal_loop_extent, only resolvable in
# physics_mode, so it never gets a LazyAllocOp in _register/_init either).

_HOST_META = """\
[ccpp-table-properties]
  name = test_suite_owned_host
  type = module
[ccpp-arg-table]
  name = test_suite_owned_host
  type = module
[ ncols ]
  standard_name = horizontal_dimension
  units = count
  type = integer
  dimensions = ()
[ pver ]
  standard_name = vertical_layer_dimension
  units = count
  type = integer
  dimensions = ()
"""

_RESIDENT_SCHEME = f"""\
[ccpp-table-properties]
  name = test_suite_owned_scheme
  type = scheme
[ccpp-arg-table]
  name = test_suite_owned_scheme_init
  type = scheme
[ my_array ]
  standard_name = test_suite_owned_var
  advected = .true.
  units = kg kg-1
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  type = real | kind = kind_phys
  memory_space = device
  intent = out
{CCPP_MANDATORY_ARGS}
"""

_NON_RESIDENT_SCHEME = f"""\
[ccpp-table-properties]
  name = test_suite_owned_scheme2
  type = scheme
[ccpp-arg-table]
  name = test_suite_owned_scheme2_init
  type = scheme
[ my_array2 ]
  standard_name = test_suite_owned_var2
  advected = .true.
  units = kg kg-1
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  type = real | kind = kind_phys
  intent = out
{CCPP_MANDATORY_ARGS}
"""

# Same standard_name declared in two tables (_init first, per _PHASE_ORDER,
# then _run) -- memory_space=device only on the SECOND-processed occurrence,
# proving the Case-4 OR-across-occurrences fix (not just reading it once on
# the first writer).
_SECOND_OCCURRENCE_SCHEME = f"""\
[ccpp-table-properties]
  name = test_suite_owned_scheme3
  type = scheme
[ccpp-arg-table]
  name = test_suite_owned_scheme3_init
  type = scheme
[ my_array3 ]
  standard_name = test_suite_owned_var3
  advected = .true.
  units = kg kg-1
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  type = real | kind = kind_phys
  intent = out
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = test_suite_owned_scheme3_run
  type = scheme
[ ncol ]
  standard_name = horizontal_loop_extent
  type = integer
  units = count
  dimensions = ()
  intent = in
[ my_array3_run ]
  standard_name = test_suite_owned_var3
  advected = .true.
  units = kg kg-1
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  type = real | kind = kind_phys
  memory_space = device
  intent = inout
{CCPP_MANDATORY_ARGS}
"""


def _suite_xml(scheme_name: str, suite_name: str = "test_suite_owned_suite") -> str:
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="{suite_name}" version="1.0">
  <group name="physics">
    <scheme>{scheme_name}</scheme>
  </group>
</suite>
"""


def _multi_scheme_suite_xml(scheme_names, suite_name: str = "test_suite_owned_suite") -> str:
    schemes = "\n".join(f"    <scheme>{name}</scheme>" for name in scheme_names)
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="{suite_name}" version="1.0">
  <group name="physics">
{schemes}
  </group>
</suite>
"""


def _multi_group_suite_xml(group_scheme_lists, suite_name: str = "test_suite_owned_suite") -> str:
    """Like _multi_scheme_suite_xml, but each element of group_scheme_lists
    is its own <group>, generating one _physicsN function per group -- used
    to prove the update-device/self injection fires independently in every
    group's function, not just once (e.g. cached) across the whole suite.
    """
    groups = []
    for i, scheme_names in enumerate(group_scheme_lists, start=1):
        schemes = "\n".join(f"    <scheme>{name}</scheme>" for name in scheme_names)
        groups.append(f'  <group name="physics{i}">\n{schemes}\n  </group>')
    groups_xml = "\n".join(groups)
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="{suite_name}" version="1.0">
{groups_xml}
</suite>
"""


# Producer/consumer pair sharing one standard_name within the SAME phase and
# group (both land in the same generated _physics function) -- the exact
# shape of the real bug: a host-only "derivation" scheme (no memory_space)
# writes a suite-owned scratch array that a later memory_space=device
# scheme reads in the same call sequence.
_PRODUCER_HOST_SCHEME = f"""\
[ccpp-table-properties]
  name = test_producer_host_scheme
  type = scheme
[ccpp-arg-table]
  name = test_producer_host_scheme_run
  type = scheme
[ my_array5 ]
  standard_name = test_suite_owned_var5
  advected = .true.
  units = kg kg-1
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  type = real | kind = kind_phys
  intent = out
{CCPP_MANDATORY_ARGS}
"""

_CONSUMER_DEVICE_SCHEME = f"""\
[ccpp-table-properties]
  name = test_consumer_device_scheme
  type = scheme
[ccpp-arg-table]
  name = test_consumer_device_scheme_run
  type = scheme
[ my_array5_b ]
  standard_name = test_suite_owned_var5
  advected = .true.
  units = kg kg-1
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  type = real | kind = kind_phys
  memory_space = device
  intent = in
{CCPP_MANDATORY_ARGS}
"""

# Symmetric reverse of the pair above: a memory_space=device scheme writes
# first, a host-only scheme reads it afterward -- must get `update self`
# before the host-only read (so it sees the device write), for parity with
# how HostMatched already handles both directions.
_PRODUCER_DEVICE_SCHEME = f"""\
[ccpp-table-properties]
  name = test_producer_device_scheme
  type = scheme
[ccpp-arg-table]
  name = test_producer_device_scheme_run
  type = scheme
[ my_array6 ]
  standard_name = test_suite_owned_var6
  advected = .true.
  units = kg kg-1
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  type = real | kind = kind_phys
  memory_space = device
  intent = out
{CCPP_MANDATORY_ARGS}
"""

_CONSUMER_HOST_SCHEME = f"""\
[ccpp-table-properties]
  name = test_consumer_host_scheme
  type = scheme
[ccpp-arg-table]
  name = test_consumer_host_scheme_run
  type = scheme
[ my_array6_b ]
  standard_name = test_suite_owned_var6
  advected = .true.
  units = kg kg-1
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  type = real | kind = kind_phys
  intent = in
{CCPP_MANDATORY_ARGS}
"""


def _fortran_output(run_host_match, ccpp_context, scheme_meta, scheme_name) -> str:
    module = run_host_match(
        scheme_metas=[scheme_meta],
        host_metas=[_HOST_META],
        suite_xml=_suite_xml(scheme_name),
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fortran_output_multi(run_host_match, ccpp_context, scheme_metas, scheme_names) -> str:
    module = run_host_match(
        scheme_metas=scheme_metas,
        host_metas=[_HOST_META],
        suite_xml=_multi_scheme_suite_xml(scheme_names),
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fortran_output_multi_group(run_host_match, ccpp_context, scheme_metas, group_scheme_lists) -> str:
    module = run_host_match(
        scheme_metas=scheme_metas,
        host_metas=[_HOST_META],
        suite_xml=_multi_group_suite_xml(group_scheme_lists),
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


# Two schemes independently pick the SAME bare local name ("dup_name") for
# TWO DIFFERENT SuiteOwned standard_names -- SuiteVariableModel._resolve_
# name_collisions qualifies both to <producing_scheme>_dup_name to avoid a
# duplicate module-scope Fortran declaration. Only scheme_collision_a's
# occurrence declares memory_space=device. This is exactly the scenario a
# Copilot review on PR #36 flagged: LazyAllocOp's var_name must use the
# resolved (possibly-qualified) name, not the scheme's own raw local name --
# otherwise the generated allocate/enter-data reference a Fortran identifier
# that was never actually declared, and _inject_suite_owned_gpu_exit's
# entries_by_name lookup (keyed by the resolved name) would never find it.
_COLLISION_SCHEME_A = f"""\
[ccpp-table-properties]
  name = test_collision_scheme_a
  type = scheme
[ccpp-arg-table]
  name = test_collision_scheme_a_init
  type = scheme
[ dup_name ]
  standard_name = test_collision_var_a
  advected = .true.
  units = kg kg-1
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  type = real | kind = kind_phys
  memory_space = device
  intent = out
{CCPP_MANDATORY_ARGS}
"""

_COLLISION_SCHEME_B = f"""\
[ccpp-table-properties]
  name = test_collision_scheme_b
  type = scheme
[ccpp-arg-table]
  name = test_collision_scheme_b_init
  type = scheme
[ dup_name ]
  standard_name = test_collision_var_b
  advected = .true.
  units = kg kg-1
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  type = real | kind = kind_phys
  intent = out
{CCPP_MANDATORY_ARGS}
"""


class TestSuiteOwnedResidency:
    def test_resident_var_gets_enter_data_inside_alloc_guard(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context, _RESIDENT_SCHEME, "test_suite_owned_scheme"
        )
        assert "if (.not. allocated(my_array)) then" in fortran
        alloc_block = fortran.split("if (.not. allocated(my_array)) then")[1]
        alloc_block = alloc_block.split("end if")[0]
        assert "allocate(my_array(" in alloc_block
        assert "#ifdef USE_GPU" in alloc_block
        assert "!$acc enter data create(my_array)" in alloc_block

    def test_resident_var_gets_module_level_declare_create(self, run_host_match, ccpp_context):
        """A runtime `!$acc enter data create(...)` alone (asserted above)
        only establishes the device buffer from inside whichever subroutine
        first allocates it. For a module-scope ALLOCATABLE array referenced
        across many separate, later subroutine calls over the life of the
        run, nvfortran also needs a companion `!$acc declare create(...)`
        at the point of declaration itself -- confirmed as the actual cause
        of a "PRESENT clause was not found on device" runtime failure that
        persisted even after the enter-data-create/update-device calls were
        verified compiling and executing correctly."""
        fortran = _fortran_output(
            run_host_match, ccpp_context, _RESIDENT_SCHEME, "test_suite_owned_scheme"
        )
        assert "real(kind=kind_phys), allocatable :: my_array(:, :)" in fortran
        decl_block = fortran.split("real(kind=kind_phys), allocatable :: my_array(:, :)")[1]
        decl_block = decl_block.split("integer :: lc_const_indices")[0]
        assert "#ifdef USE_GPU" in decl_block
        assert "!$acc declare create(my_array)" in decl_block
        assert "#endif" in decl_block

    def test_resident_var_gets_matching_exit_data_in_finalize(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context, _RESIDENT_SCHEME, "test_suite_owned_scheme"
        )
        finalize_fn = fortran.split("subroutine test_suite_owned_suite_finalize")[1]
        finalize_fn = finalize_fn.split("end subroutine test_suite_owned_suite_finalize")[0]
        assert "!$acc exit data delete(my_array)" in finalize_fn

    def test_non_resident_var_gets_no_acc_treatment(self, run_host_match, ccpp_context):
        """Regression guard: a SuiteOwned var without memory_space=device is
        completely unaffected -- matches every existing example's current
        (pre-this-feature) output."""
        fortran = _fortran_output(
            run_host_match, ccpp_context, _NON_RESIDENT_SCHEME, "test_suite_owned_scheme2"
        )
        assert "!$acc" not in fortran

    def test_second_occurrence_memory_space_still_activates_residency(
        self, run_host_match, ccpp_context
    ):
        """The Case-4 OR fix: memory_space=device declared only on the
        table processed SECOND (_run, after _init) must still activate
        residency -- not just the first-writer's own declaration.

        This shape is also a genuine divergence (the _init writer has no
        memory_space, the _run occurrence does), so it must now also get an
        `update device(...)` sync right after the host-only _init writer's
        call -- the missing piece that caused a real "PRESENT clause was
        not found on device" runtime failure for the analogous CAM-SIMA
        shape (a host-only derivation scheme feeding a memory_space=device
        scheme's input). Bare create() alone (asserted above already) only
        allocates device memory; it never moves the _init writer's host
        data onto the device for _run's later present() check to find.
        """
        fortran = _fortran_output(
            run_host_match, ccpp_context, _SECOND_OCCURRENCE_SCHEME, "test_suite_owned_scheme3"
        )
        assert "if (.not. allocated(my_array3)) then" in fortran
        alloc_block = fortran.split("if (.not. allocated(my_array3)) then")[1]
        alloc_block = alloc_block.split("end if")[0]
        assert "!$acc enter data create(my_array3)" in alloc_block
        finalize_fn = fortran.split("subroutine test_suite_owned_suite_finalize")[1]
        finalize_fn = finalize_fn.split("end subroutine test_suite_owned_suite_finalize")[0]
        assert "!$acc exit data delete(my_array3)" in finalize_fn

        init_fn = fortran.split("subroutine test_suite_owned_suite_init_physics")[1]
        init_fn = init_fn.split("end subroutine test_suite_owned_suite_init_physics")[0]
        assert "call test_suite_owned_scheme3_init(" in init_fn
        call_pos = init_fn.index("call test_suite_owned_scheme3_init(")
        assert "!$acc update self(my_array3)" in init_fn[:call_pos]
        assert "!$acc update device(my_array3)" in init_fn[call_pos:]

    def test_residency_uses_collision_qualified_name(self, run_host_match, ccpp_context):
        """Two schemes independently name a SuiteOwned var "dup_name" for two
        different standard_names -- both get qualified to
        <producing_scheme>_dup_name to avoid a duplicate module declaration.
        The enter-data/exit-data treatment must target the qualified name
        actually declared as a module var, not the raw "dup_name" neither
        scheme's own LazyAllocOp should reference (Copilot review finding,
        PR #36)."""
        fortran = _fortran_output_multi(
            run_host_match, ccpp_context,
            [_COLLISION_SCHEME_A, _COLLISION_SCHEME_B],
            ["test_collision_scheme_a", "test_collision_scheme_b"],
        )
        # The raw, unqualified name must never appear as a declared/allocated
        # Fortran identifier -- only the qualified one.
        assert "allocated(dup_name)" not in fortran
        assert "allocate(dup_name(" not in fortran
        assert "!$acc enter data create(dup_name)" not in fortran

        qualified = "test_collision_scheme_a_dup_name"
        assert f"if (.not. allocated({qualified})) then" in fortran
        alloc_block = fortran.split(f"if (.not. allocated({qualified})) then")[1]
        alloc_block = alloc_block.split("end if")[0]
        assert f"allocate({qualified}(" in alloc_block
        assert f"!$acc enter data create({qualified})" in alloc_block

        finalize_fn = fortran.split("subroutine test_suite_owned_suite_finalize")[1]
        finalize_fn = finalize_fn.split("end subroutine test_suite_owned_suite_finalize")[0]
        assert f"!$acc exit data delete({qualified})" in finalize_fn

    def test_two_scheme_same_phase_producer_consumer_gets_update_device(
        self, run_host_match, ccpp_context
    ):
        """The exact shape of the real bug: a host-only "derivation" scheme
        (no memory_space) writes a suite-owned scratch array, and a later
        memory_space=device scheme reads it -- both in the same phase and
        group, so both calls land in the same generated _physics function.
        `update device(...)` must appear between the two calls so the
        consumer's own present() check finds real data, not just an
        uninitialized device allocation."""
        fortran = _fortran_output_multi(
            run_host_match, ccpp_context,
            [_PRODUCER_HOST_SCHEME, _CONSUMER_DEVICE_SCHEME],
            ["test_producer_host_scheme", "test_consumer_device_scheme"],
        )
        physics_fn = fortran.split("subroutine test_suite_owned_suite_physics")[1]
        physics_fn = physics_fn.split("end subroutine test_suite_owned_suite_physics")[0]
        assert "call test_producer_host_scheme_run(" in physics_fn
        assert "call test_consumer_device_scheme_run(" in physics_fn
        producer_pos = physics_fn.index("call test_producer_host_scheme_run(")
        consumer_pos = physics_fn.index("call test_consumer_device_scheme_run(")
        assert producer_pos < consumer_pos
        assert "!$acc update device(my_array5)" in physics_fn[producer_pos:consumer_pos]

    def test_two_scheme_same_phase_reverse_gets_update_self(
        self, run_host_match, ccpp_context
    ):
        """Symmetric reverse of the case above: a memory_space=device scheme
        writes first, a host-only scheme reads it afterward -- `update
        self(...)` must appear between the two calls so the host-only
        reader sees the device write, matching how HostMatched already
        handles this direction."""
        fortran = _fortran_output_multi(
            run_host_match, ccpp_context,
            [_PRODUCER_DEVICE_SCHEME, _CONSUMER_HOST_SCHEME],
            ["test_producer_device_scheme", "test_consumer_host_scheme"],
        )
        physics_fn = fortran.split("subroutine test_suite_owned_suite_physics")[1]
        physics_fn = physics_fn.split("end subroutine test_suite_owned_suite_physics")[0]
        assert "call test_producer_device_scheme_run(" in physics_fn
        assert "call test_consumer_host_scheme_run(" in physics_fn
        producer_pos = physics_fn.index("call test_producer_device_scheme_run(")
        consumer_pos = physics_fn.index("call test_consumer_host_scheme_run(")
        assert producer_pos < consumer_pos
        assert "!$acc update self(my_array6)" in physics_fn[producer_pos:consumer_pos]

    def test_update_directives_fire_independently_in_every_group(
        self, run_host_match, ccpp_context
    ):
        """The same producer/consumer scheme pair, called from two separate
        groups (each gets its own generated _physicsN function) -- proves
        the update self/device injection isn't accidentally computed once
        and cached/shared across the whole suite, but fires independently
        for every function that actually contains the calls, the same way
        it would for two real per-timestep invocations."""
        fortran = _fortran_output_multi_group(
            run_host_match, ccpp_context,
            [_PRODUCER_HOST_SCHEME, _CONSUMER_DEVICE_SCHEME],
            [
                ["test_producer_host_scheme", "test_consumer_device_scheme"],
                ["test_producer_host_scheme", "test_consumer_device_scheme"],
            ],
        )
        for group_num in (1, 2):
            fn = fortran.split(f"subroutine test_suite_owned_suite_physics{group_num}")[1]
            fn = fn.split(f"end subroutine test_suite_owned_suite_physics{group_num}")[0]
            assert "call test_producer_host_scheme_run(" in fn
            assert "call test_consumer_device_scheme_run(" in fn
            producer_pos = fn.index("call test_producer_host_scheme_run(")
            consumer_pos = fn.index("call test_consumer_device_scheme_run(")
            assert producer_pos < consumer_pos
            assert "!$acc update device(my_array5)" in fn[producer_pos:consumer_pos]
