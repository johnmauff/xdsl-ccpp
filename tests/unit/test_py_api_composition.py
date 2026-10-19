"""Scheme composition through ordinary Python functions in the Python DSL.

`composite-scheme` Stage 1 (see composite_scheme_plan.md): a scheme
descriptor called from a helper function (a physics package or host
adapter) that is itself called from a suite's ``run()`` must record exactly
as if the scheme had been called directly inside ``run()``, a suite class
may define its groups as functions (``def physics_after_coupler():``), and
``with forLoop("std_name"):`` blocks may appear in any of those bodies.
"""

import pytest

from xdsl_ccpp.dialects.ccpp import SchemeOp, SubcycleOp
from xdsl_ccpp.frontend import py_api
from xdsl_ccpp.frontend.py_api import (
    SchemeDescriptor,
    SubcycleDescriptor,
    build_ir,
    ccpp_suite,
    forLoop,
)

scheme_a = SchemeDescriptor("scheme_a", {})
scheme_b = SchemeDescriptor("scheme_b", {})
scheme_c = SchemeDescriptor("scheme_c", {})
# Bound to a Python name that differs from its scheme name, as a package
# module would do (e.g. ``sw_rte = _s("rrtmgp_sw_rte")``).
short_alias = SchemeDescriptor("long_scheme_name", {})


def package_ab():
    scheme_a()
    scheme_b()


def package_outer():
    package_ab()
    scheme_c(var_x=3)


def package_alias():
    short_alias()


def _recorded(suite):
    """[(group, scheme_name, overrides)] in recording order."""
    return [(group, sd.name, overrides)
            for group, items in suite.groups.items()
            for sd, overrides in items]


class TestDescriptorCall:
    def test_call_outside_recording_raises(self):
        with pytest.raises(RuntimeError, match="outside a suite recording"):
            scheme_a()

    def test_helper_records_in_order(self):
        @ccpp_suite("s", version="1.0")
        class s:
            physics = [scheme_a, scheme_b, scheme_c]

            def run():
                package_ab()
                scheme_c()

        assert _recorded(s) == [
            ("physics", "scheme_a", {}),
            ("physics", "scheme_b", {}),
            ("physics", "scheme_c", {}),
        ]

    def test_nested_helpers_and_overrides(self):
        @ccpp_suite("s", version="1.0")
        class s:
            physics = [scheme_a, scheme_b, scheme_c]

            def run():
                package_outer()

        assert _recorded(s) == [
            ("physics", "scheme_a", {}),
            ("physics", "scheme_b", {}),
            ("physics", "scheme_c", {"var_x": "3"}),
        ]

    def test_helper_schemes_record_into_their_parent_group(self):
        @ccpp_suite("s", version="1.0")
        class s:
            before = [scheme_a, scheme_b]
            after = [scheme_c]

            def run():
                package_outer()

        assert _recorded(s) == [
            ("before", "scheme_a", {}),
            ("before", "scheme_b", {}),
            ("after", "scheme_c", {"var_x": "3"}),
        ]

    def test_alias_bound_descriptor_records_its_scheme_name(self):
        @ccpp_suite("s", version="1.0")
        class s:
            physics = [short_alias]

            def run():
                package_alias()

        assert _recorded(s) == [("physics", "long_scheme_name", {})]

    def test_recorder_cleared_after_run(self):
        @ccpp_suite("s", version="1.0")
        class s:
            physics = [scheme_a]

            def run():
                package_ab()

        assert py_api._active_recorder is None

    def test_recorder_cleared_after_run_raises(self):
        def failing_helper():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            py_api._run_groups(failing_helper, {"physics": [scheme_a]})
        assert py_api._active_recorder is None


class TestIdenticalIR:
    def test_helper_composition_matches_flat_run(self):
        """Composing through helpers produces the same IR as listing the
        same schemes directly in run() -- Stage 1's core invariant."""

        @ccpp_suite("s", version="1.0")
        class flat:
            physics = [scheme_a, scheme_b, scheme_c]

            def run():
                scheme_a()
                scheme_b()
                scheme_c(var_x=3)

        @ccpp_suite("s", version="1.0")
        class composed:
            physics = [scheme_a, scheme_b, scheme_c]

            def run():
                package_outer()

        assert str(build_ir(composed)) == str(build_ir(flat))


class TestGroupFunctions:
    def test_group_function_records_calls(self):
        @ccpp_suite("s", version="1.0")
        class s:
            def physics_after_coupler():
                package_outer()

        assert _recorded(s) == [
            ("physics_after_coupler", "scheme_a", {}),
            ("physics_after_coupler", "scheme_b", {}),
            ("physics_after_coupler", "scheme_c", {"var_x": "3"}),
        ]

    def test_group_functions_and_lists_keep_definition_order(self):
        @ccpp_suite("s", version="1.0")
        class s:
            def before():
                package_ab()

            middle = [scheme_c]

            def after():
                scheme_a()

        assert list(s.groups) == ["before", "middle", "after"]
        assert _recorded(s) == [
            ("before", "scheme_a", {}),
            ("before", "scheme_b", {}),
            ("middle", "scheme_c", {}),
            ("after", "scheme_a", {}),
        ]

    def test_group_function_ignores_list_membership(self):
        """A scheme that also appears in another group's list still records
        into the group function that called it."""

        @ccpp_suite("s", version="1.0")
        class s:
            listed = [scheme_a]

            def fn_group():
                scheme_a()

        assert _recorded(s) == [("listed", "scheme_a", {}),
                                ("fn_group", "scheme_a", {})]

    def test_private_functions_are_not_groups(self):
        @ccpp_suite("s", version="1.0")
        class s:
            def _helper():
                scheme_b()

            def physics():
                scheme_a()

        assert list(s.groups) == ["physics"]

    def test_run_and_group_functions_together_rejected(self):
        with pytest.raises(ValueError, match="both run\\(\\) and group function"):
            @ccpp_suite("s", version="1.0")
            class s:
                physics = [scheme_a]

                def run():
                    scheme_a()

                def other():
                    scheme_b()

    def test_group_function_may_use_enclosing_locals(self):
        local_scheme = SchemeDescriptor("local_scheme", {})

        def local_package():
            local_scheme(var_y=1)

        @ccpp_suite("s", version="1.0")
        class s:
            def physics():
                local_package()

        assert _recorded(s) == [("physics", "local_scheme", {"var_y": "1"})]

    def test_run_may_use_enclosing_locals(self):
        """run() is re-executed with its closure, so locals of an enclosing
        function work there too (previously only module globals did)."""
        local_scheme = SchemeDescriptor("local_scheme", {})

        @ccpp_suite("s", version="1.0")
        class s:
            physics = [scheme_a]

            def run():
                scheme_a()
                local_scheme()

        assert _recorded(s) == [("physics", "scheme_a", {}),
                                ("physics", "local_scheme", {})]

    def test_group_function_matches_list_group_ir(self):
        @ccpp_suite("s", version="1.0")
        class listed:
            physics = [scheme_a, scheme_b]

        @ccpp_suite("s", version="1.0")
        class fn:
            def physics():
                package_ab()

        assert str(build_ir(fn)) == str(build_ir(listed))


N = "number_of_diagnostic_subcycles"


def looped_package():
    scheme_a()
    with forLoop(N):
        scheme_b()
        scheme_c(var_x=3)


class TestForLoopBlock:
    def test_block_in_group_function_records_one_subcycle(self):
        @ccpp_suite("s", version="1.0")
        class s:
            def physics():
                looped_package()

        items = s.groups["physics"]
        assert items[0] == (scheme_a, {})
        loop = items[1]
        assert isinstance(loop, SubcycleDescriptor)
        assert loop.count == N
        assert loop.schemes == [(scheme_b, {}), (scheme_c, {"var_x": "3"})]

    def test_block_matches_list_form_ir(self):
        @ccpp_suite("s", version="1.0")
        class listed:
            physics = [scheme_a, forLoop(N, [scheme_b, scheme_c])]

        @ccpp_suite("s", version="1.0")
        class block:
            def physics():
                scheme_a()
                with forLoop(N):
                    scheme_b()
                    scheme_c()

        assert str(build_ir(block)) == str(build_ir(listed))

    def test_overrides_inside_loop_are_kept(self):
        @ccpp_suite("s", version="1.0")
        class s:
            def physics():
                looped_package()

        module = build_ir(s)
        subcycles = [op for op in module.walk() if isinstance(op, SubcycleOp)]
        assert len(subcycles) == 1
        inner = {op.scheme_name.data: op.arg_overrides
                 for op in subcycles[0].walk() if isinstance(op, SchemeOp)}
        assert inner["scheme_b"] is None
        assert {k: v.data for k, v in inner["scheme_c"].data.items()} == {"var_x": "3"}

    def test_nested_blocks(self):
        @ccpp_suite("s", version="1.0")
        class s:
            def physics():
                with forLoop(N):
                    scheme_a()
                    with forLoop(2):
                        scheme_b()

        (outer,) = s.groups["physics"]
        assert outer.count == N
        assert outer.schemes[0] == (scheme_a, {})
        inner = outer.schemes[1]
        assert isinstance(inner, SubcycleDescriptor)
        assert inner.count == 2 and inner.schemes == [(scheme_b, {})]
        module = build_ir(s)
        loops = [op for op in module.walk() if isinstance(op, SubcycleOp)]
        assert [op.loop_count.data for op in loops] == [N, "2"]
        assert [bool(op.is_literal.value.data) for op in loops] == [False, True]

    def test_block_in_run_by_name_and_via_helper(self):
        """In run(), by-name calls inside the block land in the loop, and the
        loop lands in its schemes' parent group."""

        @ccpp_suite("s", version="1.0")
        class s:
            before = [scheme_a]
            after = [scheme_b, scheme_c]

            def run():
                scheme_a()
                with forLoop(N):
                    scheme_b()
                    scheme_c(var_x=3)

        assert s.groups["before"] == [(scheme_a, {})]
        (loop,) = s.groups["after"]
        assert loop.schemes == [(scheme_b, {}), (scheme_c, {"var_x": "3"})]

    def test_block_in_run_spanning_groups_rejected(self):
        with pytest.raises(ValueError, match="several groups"):
            @ccpp_suite("s", version="1.0")
            class s:
                before = [scheme_a]
                after = [scheme_b]

                def run():
                    with forLoop(N):
                        scheme_a()
                        scheme_b()

    def test_block_outside_recording_raises(self):
        with pytest.raises(RuntimeError, match="outside a suite recording"):
            with forLoop(N):
                pass

    def test_empty_block_rejected(self):
        with pytest.raises(ValueError, match="recorded no scheme calls"):
            @ccpp_suite("s", version="1.0")
            class s:
                def physics():
                    with forLoop(N):
                        pass

    def test_list_form_used_as_block_rejected(self):
        with pytest.raises(ValueError, match="one form or the other"):
            @ccpp_suite("s", version="1.0")
            class s:
                def physics():
                    with forLoop(N, [scheme_a]):
                        scheme_b()

    def test_exception_in_block_restores_recorders(self):
        with pytest.raises(KeyError):
            @ccpp_suite("s", version="1.0")
            class s:
                def physics():
                    with forLoop(N):
                        scheme_a()
                        raise KeyError("boom")
        assert py_api._active_recorder is None
