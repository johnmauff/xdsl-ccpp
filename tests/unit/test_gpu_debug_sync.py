"""Unit tests for `--gpu-debug-sync`: an extra `!$acc update self(...)`
emitted immediately after every scheme call that writes (intent out/inout)
a memory_space=device variable, regardless of whether that variable's
residency treatment otherwise needs one.

Debug-only aid for host-memory-only tools (e.g. dropsonde) that have no
OpenACC/device awareness -- see GPUDataPass._build_debug_sync_touches/
SuiteCAP-side GenerateSuiteSubroutine._build_suite_owned_debug_sync_touches
and cap_shared.emit_coalesced_updates, whose (id(first_op), id(last_op))
grouping both mechanisms feed into.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.gpu_data_pass import GPUDataPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

import pytest

pytestmark = pytest.mark.usefixtures("legacy_mode")


def _fortran_output(run_host_match, ccpp_context, scheme_metas, host_metas, suite_xml, debug_sync) -> str:
    module = run_host_match(
        scheme_metas=scheme_metas,
        host_metas=host_metas,
        suite_xml=suite_xml,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP(debug_sync=debug_sync).apply(ccpp_context, module)
    GPUDataPass(directive="acc", debug_sync=debug_sync).apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fn_body(fortran: str, fn_name: str) -> str:
    return fortran.split(f"subroutine {fn_name}")[1].split(f"end subroutine {fn_name}")[0]


# ── no-divergence fixtures: each var is touched by exactly one scheme, so ──
# ── none of them are "diverged" -- today this means NO update self/device ──
# ── is ever emitted; --gpu-debug-sync should add one anyway. ───────────────

_HOST_MATCHED_SCHEME = f"""\
[ccpp-table-properties]
  name = test_sync_host_scheme
  type = scheme
[ccpp-arg-table]
  name = test_sync_host_scheme_run
  type = scheme
[ out_var ]
  standard_name = test_sync_host_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = out
{CCPP_MANDATORY_ARGS}
"""

_HOST_MATCHED_HOST = """\
[ccpp-table-properties]
  name = test_sync_host_mod
  type = module
[ccpp-arg-table]
  name = test_sync_host_mod
  type = module
[ out_var ]
  standard_name = test_sync_host_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
"""

_HOST_MATCHED_SUITE_XML = minimal_suite_xml(
    "test_sync_host_scheme", suite_name="test_sync_host_suite"
)

_REGISTER_TABLE_LINES = """\
[ dyn_const ]
  standard_name = dynamic_constituents_for_{name}
  dimensions = (:)
  type = ccpp_constituent_properties_t
  intent = out
  allocatable = true
[ errmsg ]
  standard_name = ccpp_error_message
  units = none
  dimensions = ()
  type = character
  kind = len=512
  intent = out
[ errflg ]
  standard_name = ccpp_error_code
  units = 1
  dimensions = ()
  type = integer
  intent = out
"""

_CAPSCRATCH_SCHEME = f"""\
[ccpp-table-properties]
  name = test_sync_cs_scheme
  type = scheme
[ccpp-arg-table]
  name = test_sync_cs_scheme_register
  type = scheme
{_REGISTER_TABLE_LINES.format(name="test_sync_cs")}
[ccpp-arg-table]
  name = test_sync_cs_scheme_run
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

_CAPSCRATCH_SUITE_XML = minimal_suite_xml(
    "test_sync_cs_scheme", suite_name="test_sync_cs_suite"
)

_SUITE_OWNED_HOST = """\
[ccpp-table-properties]
  name = test_sync_so_host
  type = module
[ccpp-arg-table]
  name = test_sync_so_host
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

_SUITE_OWNED_SCHEME = f"""\
[ccpp-table-properties]
  name = test_sync_so_scheme
  type = scheme
[ccpp-arg-table]
  name = test_sync_so_scheme_init
  type = scheme
[ my_array ]
  standard_name = test_sync_so_var
  advected = .true.
  units = kg kg-1
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  type = real | kind = kind_phys
  memory_space = device
  intent = out
{CCPP_MANDATORY_ARGS}
"""

_SUITE_OWNED_SUITE_XML = minimal_suite_xml(
    "test_sync_so_scheme", suite_name="test_sync_so_suite"
)


class TestDebugSyncNoDivergence:
    def test_host_matched_var_gets_update_self_after_producing_call(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_HOST_MATCHED_SCHEME], [_HOST_MATCHED_HOST], _HOST_MATCHED_SUITE_XML,
            debug_sync=True,
        )
        suite_fn = _fn_body(fortran, "test_sync_host_suite_physics")
        assert "call test_sync_host_scheme_run(" in suite_fn
        call_pos = suite_fn.index("call test_sync_host_scheme_run(")
        assert "update self(out_var)" in suite_fn[call_pos:]

    def test_capscratch_var_gets_update_self_after_producing_call(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_CAPSCRATCH_SCHEME], [], _CAPSCRATCH_SUITE_XML,
            debug_sync=True,
        )
        suite_fn = _fn_body(fortran, "test_sync_cs_suite_physics")
        assert "call test_sync_cs_scheme_run(" in suite_fn
        call_pos = suite_fn.index("call test_sync_cs_scheme_run(")
        assert "update self(const_tend)" in suite_fn[call_pos:]

    def test_suite_owned_var_gets_update_self_after_producing_call(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_SUITE_OWNED_SCHEME], [_SUITE_OWNED_HOST], _SUITE_OWNED_SUITE_XML,
            debug_sync=True,
        )
        init_fn = _fn_body(fortran, "test_sync_so_suite_init_physics")
        assert "call test_sync_so_scheme_init(" in init_fn
        call_pos = init_fn.index("call test_sync_so_scheme_init(")
        assert "!$acc update self(my_array)" in init_fn[call_pos:]

    def test_no_update_self_anywhere_when_debug_sync_off(
        self, run_host_match, ccpp_context
    ):
        """Regression guard: with the flag off, behavior is byte-identical
        to before this feature existed -- none of these (non-diverged)
        vars get any update self/device at all."""
        for scheme, host, suite_xml in (
            (_HOST_MATCHED_SCHEME, [_HOST_MATCHED_HOST], _HOST_MATCHED_SUITE_XML),
            (_CAPSCRATCH_SCHEME, [], _CAPSCRATCH_SUITE_XML),
            (_SUITE_OWNED_SCHEME, [_SUITE_OWNED_HOST], _SUITE_OWNED_SUITE_XML),
        ):
            fortran = _fortran_output(
                run_host_match, ccpp_context, [scheme], host, suite_xml, debug_sync=False,
            )
            assert "update self(" not in fortran


# ── merging fixtures ─────────────────────────────────────────────────────────

_TWO_VAR_SCHEME = f"""\
[ccpp-table-properties]
  name = test_sync_two_var_scheme
  type = scheme
[ccpp-arg-table]
  name = test_sync_two_var_scheme_run
  type = scheme
[ var_a ]
  standard_name = test_sync_var_a
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = out
[ var_b ]
  standard_name = test_sync_var_b
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = out
{CCPP_MANDATORY_ARGS}
"""

_TWO_VAR_HOST = """\
[ccpp-table-properties]
  name = test_sync_two_var_host
  type = module
[ccpp-arg-table]
  name = test_sync_two_var_host
  type = module
[ var_a ]
  standard_name = test_sync_var_a
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
[ var_b ]
  standard_name = test_sync_var_b
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
"""

_TWO_VAR_SUITE_XML = minimal_suite_xml(
    "test_sync_two_var_scheme", suite_name="test_sync_two_var_suite"
)

_DUAL_CALL_SCHEME_A = f"""\
[ccpp-table-properties]
  name = test_sync_dual_scheme_a
  type = scheme
[ccpp-arg-table]
  name = test_sync_dual_scheme_a_run
  type = scheme
[ out_var ]
  standard_name = test_sync_dual_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = out
{CCPP_MANDATORY_ARGS}
"""

_DUAL_CALL_SCHEME_B = f"""\
[ccpp-table-properties]
  name = test_sync_dual_scheme_b
  type = scheme
[ccpp-arg-table]
  name = test_sync_dual_scheme_b_run
  type = scheme
[ out_var ]
  standard_name = test_sync_dual_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = out
{CCPP_MANDATORY_ARGS}
"""

_DUAL_CALL_HOST = """\
[ccpp-table-properties]
  name = test_sync_dual_host
  type = module
[ccpp-arg-table]
  name = test_sync_dual_host
  type = module
[ out_var ]
  standard_name = test_sync_dual_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
"""

_DUAL_CALL_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_sync_dual_suite" version="1.0">
  <group name="physics">
    <scheme>test_sync_dual_scheme_a</scheme>
    <scheme>test_sync_dual_scheme_b</scheme>
  </group>
</suite>
"""

# Diverged host var (qv) plus a SEPARATE device-producing var (zz_var,
# unrelated to the divergence) written by the SAME call that terminates
# qv's own update run -- proves a "produced" (debug-sync) touch and a
# diverged var's own "update"-run touch sharing a call boundary coexist
# correctly as two independent directives (self-before/device-after for
# qv, self-after-only for zz_var) rather than corrupting or wrongly
# cross-merging into one nonsensical combined directive -- these are
# opposite-direction syncs (self vs device) at a shared point, so unlike
# two "produced" touches sharing a call, they can never actually merge
# into one call; only same-direction, same-timing touches do (see
# test_two_vars_same_call_get_one_combined_update_self above). qv_a's own
# arg is deliberately intent=in (read-only) here, not inout -- an inout
# device arg would ALSO count as its own separate "produced" touch (a
# scheme can genuinely have some host-only args and some on-device-compute
# args in the same call), which would add a third, unrelated sync point
# and muddy this specific two-directions-coexist scenario.

_MERGE_SCHEME_A = f"""\
[ccpp-table-properties]
  name = test_sync_merge_scheme_a
  type = scheme
[ccpp-arg-table]
  name = test_sync_merge_scheme_a_run
  type = scheme
[ qv_a ]
  standard_name = test_sync_merge_conflict_var
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = in
{CCPP_MANDATORY_ARGS}
"""

_MERGE_SCHEME_B = f"""\
[ccpp-table-properties]
  name = test_sync_merge_scheme_b
  type = scheme
[ccpp-arg-table]
  name = test_sync_merge_scheme_b_run
  type = scheme
[ qv_b ]
  standard_name = test_sync_merge_conflict_var
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
[ zz_var ]
  standard_name = test_sync_merge_extra_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = out
{CCPP_MANDATORY_ARGS}
"""

_MERGE_HOST = """\
[ccpp-table-properties]
  name = test_sync_merge_host
  type = module
[ccpp-arg-table]
  name = test_sync_merge_host
  type = module
[ conflict_var ]
  standard_name = test_sync_merge_conflict_var
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
[ extra_var ]
  standard_name = test_sync_merge_extra_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
"""

_MERGE_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_sync_merge_suite" version="1.0">
  <group name="physics">
    <scheme>test_sync_merge_scheme_a</scheme>
    <scheme>test_sync_merge_scheme_b</scheme>
  </group>
</suite>
"""


class TestDebugSyncMerging:
    def test_two_vars_same_call_get_one_combined_update_self(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_TWO_VAR_SCHEME], [_TWO_VAR_HOST], _TWO_VAR_SUITE_XML,
            debug_sync=True,
        )
        suite_fn = _fn_body(fortran, "test_sync_two_var_suite_physics")
        assert suite_fn.count("update self(") == 1
        self_line = next(line for line in suite_fn.splitlines() if "update self(" in line)
        assert "var_a" in self_line and "var_b" in self_line

    def test_same_var_two_different_calls_stays_two_separate_syncs(
        self, run_host_match, ccpp_context
    ):
        """No temporal coalescing: the same var written by two different,
        consecutive calls must NOT be merged into a single sync after the
        second call -- each producing call gets its own, so a debugger
        reading in between sees each call's own contribution."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_DUAL_CALL_SCHEME_A, _DUAL_CALL_SCHEME_B], [_DUAL_CALL_HOST],
            _DUAL_CALL_SUITE_XML, debug_sync=True,
        )
        suite_fn = _fn_body(fortran, "test_sync_dual_suite_physics")
        assert suite_fn.count("update self(out_var)") == 2
        assert "call test_sync_dual_scheme_a_run(" in suite_fn
        assert "call test_sync_dual_scheme_b_run(" in suite_fn
        a_pos = suite_fn.index("call test_sync_dual_scheme_a_run(")
        b_pos = suite_fn.index("call test_sync_dual_scheme_b_run(")
        assert a_pos < b_pos
        # One sync between the two calls (for scheme_a's own write), one
        # sync after scheme_b's own call.
        assert "update self(out_var)" in suite_fn[a_pos:b_pos]
        assert "update self(out_var)" in suite_fn[b_pos:]

    def test_debug_sync_touch_coexists_with_diverged_var_at_same_call(
        self, run_host_match, ccpp_context
    ):
        """qv's own divergence run ends at scheme_b's call (the "update"
        side, needing a self-before + device-after pair around it); zz_var
        is an unrelated device-producing var ALSO written by that same
        call, needing only a self-after (produced) sync. These are
        opposite-direction syncs at the same point, so they must NOT be
        cross-merged into one nonsensical directive -- each stays its own,
        correct, independent directive, proving the two mechanisms coexist
        without corrupting each other."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_MERGE_SCHEME_A, _MERGE_SCHEME_B], [_MERGE_HOST],
            _MERGE_SUITE_XML, debug_sync=True,
        )
        suite_fn = _fn_body(fortran, "test_sync_merge_suite_physics")
        assert "call test_sync_merge_scheme_b_run(" in suite_fn
        call_pos = suite_fn.index("call test_sync_merge_scheme_b_run(")

        # qv's own divergence run: self-before + device-after, unaffected
        # by zz_var's presence.
        assert "update self(qv_a)" in suite_fn[:call_pos]
        assert "update device(qv_a)" in suite_fn[call_pos:]

        # zz_var's own produced (debug-sync) touch: self-after only, right
        # after the same call -- never a device push, never merged into
        # qv's own directives.
        assert "update self(zz_var)" in suite_fn[call_pos:]
        assert "update device(zz_var)" not in suite_fn
        assert "update self(qv_a, zz_var)" not in suite_fn
        assert "update self(zz_var, qv_a)" not in suite_fn
        assert "update device(qv_a, zz_var)" not in suite_fn
