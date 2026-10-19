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


class TestSchemeFromSource:
    """ccpp_scheme_from_source: examples/helloworld_composite's tagged schemes
    must load identically to examples/helloworld's hand-written .meta."""

    @pytest.mark.parametrize("scheme", ["hello_scheme", "temp_adjust"])
    def test_tagged_source_matches_meta_ir(self, scheme):
        from_meta = py_api.ccpp_scheme_from_meta(f"examples/helloworld/{scheme}.meta")
        from_source = py_api.ccpp_scheme_from_source(f"examples/helloworld_composite/{scheme}.F90")
        assert from_source.name == from_meta.name == scheme
        assert sorted(from_source.entry_points) == sorted(from_meta.entry_points)

        @ccpp_suite("s", version="1.0")
        class via_meta:
            physics = [from_meta]

        @ccpp_suite("s", version="1.0")
        class via_source:
            physics = [from_source]

        assert str(build_ir(via_source)) == str(build_ir(via_meta))

    def test_unreadable_source_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Could not extract CCPP metadata"):
            py_api.ccpp_scheme_from_source(str(tmp_path / "missing.F90"))


H = "examples/helloworld"
HC = "examples/helloworld_composite"
ref_hello = py_api.ccpp_scheme_ref("hello_scheme")
ref_adjust = py_api.ccpp_scheme_ref("temp_adjust")


def _table_names(module):
    from xdsl_ccpp.dialects.ccpp import TablePropertiesOp
    return [op.table_name.data for op in module.body.block.ops
            if isinstance(op, TablePropertiesOp)]


@ccpp_suite("s", version="1.0")
class ref_suite:
    def physics():
        ref_hello()
        ref_adjust()


class TestSchemeReferences:
    """ccpp_scheme_ref: path-free scheme references, resolved by name from
    scheme_files (or left to the driver), as for an XML suite."""

    def _full_suite_ir(self, **kwargs):
        hello = py_api.ccpp_scheme_from_meta(f"{H}/hello_scheme.meta")
        adjust = py_api.ccpp_scheme_from_meta(f"{H}/temp_adjust.meta")

        @ccpp_suite("s", version="1.0")
        class full:
            def physics():
                hello()
                adjust()

        return str(build_ir(full, **kwargs))

    def test_reference_records_like_a_scheme(self):
        assert _recorded(ref_suite) == [("physics", "hello_scheme", {}),
                                        ("physics", "temp_adjust", {})]

    def test_unresolved_references_emit_no_metadata(self):
        """Without scheme_files the driver supplies the metadata."""
        assert _table_names(build_ir(ref_suite)) == []

    @pytest.mark.parametrize("files", [
        [f"{H}/hello_scheme.meta", f"{H}/temp_adjust.meta"],
        [f"{HC}/hello_scheme.F90", f"{HC}/temp_adjust.F90"],
    ])
    def test_references_resolve_from_meta_or_tagged_source(self, files):
        assert str(build_ir(ref_suite, scheme_files=files)) == self._full_suite_ir()

    def test_multi_scheme_meta_file(self, tmp_path):
        combined = tmp_path / "both.meta"
        combined.write_text(open(f"{H}/hello_scheme.meta").read() + "\n"
                            + open(f"{H}/temp_adjust.meta").read())
        assert str(build_ir(ref_suite, scheme_files=[str(combined)])) == self._full_suite_ir()

    def test_missing_metadata_raises(self):
        with pytest.raises(ValueError, match="No metadata for scheme 'temp_adjust'"):
            build_ir(ref_suite, scheme_files=[f"{H}/hello_scheme.meta"])

    def test_duplicate_scheme_raises(self):
        with pytest.raises(ValueError, match="defined more than once"):
            build_ir(ref_suite, scheme_files=[f"{H}/hello_scheme.meta",
                                              f"{HC}/hello_scheme.F90",
                                              f"{H}/temp_adjust.meta"])

    def test_full_descriptor_wins_over_reference(self):
        full_hello = py_api.ccpp_scheme_from_meta(f"{H}/hello_scheme.meta")

        @ccpp_suite("s", version="1.0")
        class mixed:
            def physics():
                ref_hello()
                full_hello()

        assert _table_names(build_ir(mixed)) == ["hello_scheme"]

    def test_host_files_follow_additional(self):
        hosts = [f"{H}/hello_world_host.meta", f"{H}/hello_world_mod.meta"]
        expected = self._full_suite_ir(
            additional=py_api.ccpp_host_from_meta(hosts[0])
            + py_api.ccpp_host_from_meta(hosts[1]))
        got = str(build_ir(ref_suite,
                           scheme_files=[f"{H}/hello_scheme.meta", f"{H}/temp_adjust.meta"],
                           host_files=hosts))
        assert got == expected

    @pytest.mark.parametrize("entry", ["export_suite", "emit_ir"])
    def test_export_suite_reads_files_from_argv(self, entry, monkeypatch, capsys):
        """export_suite (and its older name emit_ir) take metadata from argv."""
        files = f"{H}/hello_scheme.meta,{H}/temp_adjust.meta"
        monkeypatch.setattr("sys.argv", ["suite.py", f"--scheme-files={files}"])
        getattr(py_api, entry)(ref_suite)
        assert capsys.readouterr().out.strip() == self._full_suite_ir().strip()
