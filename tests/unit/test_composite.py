"""Composite schemes in the IR (composite-scheme Stage 2, S2-1 and S2-2).

A ``@ccpp_composite`` function or package entry point records one
``ccpp.composite`` op per call (py_api.py), and the ``flatten-composites``
pass inlines composites again, so the flattened IR is identical to that of
the same suite written without the decorator (composite_scheme_plan.md
§11.3).  Entry points are tagged with their package, and host code they run
through hooks is recorded as nested composites marked ``hook``.
"""

import pytest

from xdsl_ccpp.dialects.ccpp import CompositeOp, SchemeOp, SubcycleOp
from xdsl_ccpp.frontend import py_api
from xdsl_ccpp.frontend.py_api import (
    CompositeDescriptor,
    SchemeDescriptor,
    SubcycleDescriptor,
    build_ir,
    ccpp_composite,
    ccpp_package,
    ccpp_suite,
    forLoop,
)
from xdsl_ccpp.tools.ctx_utils import make_ccpp_context
from xdsl_ccpp.transforms.flatten_composites import FlattenComposites

N = "number_of_diagnostic_subcycles"
scheme_a = SchemeDescriptor("scheme_a", {})
scheme_b = SchemeDescriptor("scheme_b", {})
scheme_c = SchemeDescriptor("scheme_c", {})


# The same package written twice: plain functions (flattened while recording)
# and @ccpp_composite functions (recorded as composites).
def plain_inner():
    scheme_b()
    scheme_c(var_x=3)


def plain_outer(*, hook):
    scheme_a()
    with forLoop(N):
        plain_inner()
        hook()


@ccpp_composite
def comp_inner():
    scheme_b()
    scheme_c(var_x=3)


@ccpp_composite
def comp_outer(*, hook):
    scheme_a()
    with forLoop(N):
        comp_inner()
        hook()


@ccpp_suite("s", version="1.0")
class plain_suite:
    def physics():
        plain_outer(hook=scheme_a)
        scheme_c()


@ccpp_suite("s", version="1.0")
class composite_suite:
    def physics():
        comp_outer(hook=scheme_a)
        scheme_c()


def _flattened(suite) -> str:
    module = build_ir(suite)
    FlattenComposites().apply(make_ccpp_context(), module)
    return str(module)


def _ops(module, op_type):
    return [op for op in module.walk() if isinstance(op, op_type)]


class TestRecording:
    def test_composite_call_records_one_descriptor(self):
        (outer, last) = composite_suite.groups["physics"]
        assert isinstance(outer, CompositeDescriptor)
        assert outer.name == "comp_outer"
        assert last == (scheme_c, {})

    def test_body_order_loops_nesting_and_overrides(self):
        outer = composite_suite.groups["physics"][0]
        assert outer.items[0] == (scheme_a, {})
        loop = outer.items[1]
        assert isinstance(loop, SubcycleDescriptor) and loop.count == N
        inner = loop.schemes[0]
        assert isinstance(inner, CompositeDescriptor) and inner.name == "comp_inner"
        assert inner.items == [(scheme_b, {}), (scheme_c, {"var_x": "3"})]
        assert loop.schemes[1] == (scheme_a, {})

    def test_composite_called_outside_recording_raises(self):
        with pytest.raises(RuntimeError, match="outside a suite recording"):
            comp_inner()

    def test_empty_composite_raises(self):
        @ccpp_composite
        def empty():
            pass

        with pytest.raises(ValueError, match="recorded no scheme calls"):
            @ccpp_suite("s", version="1.0")
            class s:
                def physics():
                    empty()

    def test_recorder_restored_after_composite(self):
        assert py_api._active_recorder is None

    def test_composite_in_run_lands_in_its_schemes_group(self):
        @ccpp_suite("s", version="1.0")
        class s:
            before = [scheme_a]
            after = [scheme_b, scheme_c]

            def run():
                scheme_a()
                comp_inner()

        assert s.groups["before"] == [(scheme_a, {})]
        (inner,) = s.groups["after"]
        assert isinstance(inner, CompositeDescriptor) and inner.name == "comp_inner"

    def test_composite_in_run_spanning_groups_rejected(self):
        @ccpp_composite
        def spans():
            scheme_a()
            scheme_b()

        with pytest.raises(ValueError, match="composite 'spans'.*several groups"):
            @ccpp_suite("s", version="1.0")
            class s:
                before = [scheme_a]
                after = [scheme_b]

                def run():
                    spans()


class TestIR:
    def test_composites_become_ops_with_bodies(self):
        module = build_ir(composite_suite)
        composites = _ops(module, CompositeOp)
        assert [op.composite_name.data for op in composites] == ["comp_outer", "comp_inner"]
        inner_schemes = [op.scheme_name.data for op in composites[1].walk()
                         if isinstance(op, SchemeOp)]
        assert inner_schemes == ["scheme_b", "scheme_c"]
        assert len(_ops(module, SubcycleOp)) == 1

    def test_scheme_tables_registered_once_inside_composites(self):
        module = str(build_ir(composite_suite))
        assert module.count("ccpp.table_properties") == 3


class TestFlatten:
    def test_flattened_ir_identical_to_plain_suite(self):
        """S2-1's core invariant: composites change the IR only until they
        are flattened."""
        assert _flattened(composite_suite) == str(build_ir(plain_suite))

    def test_flatten_removes_every_composite(self):
        module = build_ir(composite_suite)
        FlattenComposites().apply(make_ccpp_context(), module)
        assert _ops(module, CompositeOp) == []
        assert len(_ops(module, SubcycleOp)) == 1

    def test_flatten_leaves_composite_free_module_unchanged(self):
        assert _flattened(plain_suite) == str(build_ir(plain_suite))


class TestDriverIntegration:
    """S2-1 step (b): tools that read the frontend's IR before any pass
    runs understand composites, and ccpp_dsl flattens them first (after
    scoping packages, S2-2)."""

    def test_datatable_finds_schemes_inside_composites(self):
        from xdsl_ccpp.tools.ccpp_datatable import _used_scheme_names

        assert _used_scheme_names(build_ir(composite_suite)) == {
            "scheme_a", "scheme_b", "scheme_c"}

    def test_pipeline_scopes_then_flattens_composites_first(self):
        from xdsl_ccpp.tools.ccpp_dsl import ccppMain

        tool = ccppMain()
        options_db = tool.default_options_db()
        options_db.update({"suites": ["examples/helloworld/hello_world_suite.xml"],
                           "scheme_files": ["examples/helloworld/hello_scheme.meta"],
                           "host_files": [], "verbose": 0})
        tool.options_db = tool._normalize_options_db(dict(options_db))
        assert tool._build_pipeline().split(",")[:2] == ["scope-packages",
                                                          "flatten-composites"]

    def test_composite_python_suite_generates_same_caps_as_xml(self, tmp_path):
        """A Python suite whose package is a @ccpp_composite generates, through
        ccpp_dsl, exactly the Fortran the XML suite does."""
        import os

        from xdsl_ccpp.tools.ccpp_dsl import ccppMain

        h = "examples/helloworld"
        script = tmp_path / "composite_suite.py"
        script.write_text(
            "from xdsl_ccpp.frontend.py_api import (ccpp_composite, ccpp_scheme_ref,\n"
            "                                       ccpp_suite, export_suite)\n"
            "hello_scheme = ccpp_scheme_ref('hello_scheme')\n"
            "temp_adjust = ccpp_scheme_ref('temp_adjust')\n"
            "@ccpp_composite\n"
            "def hello_package(*, adjust, greet=hello_scheme):\n"
            "    greet()\n"
            "    adjust()\n"
            "@ccpp_suite('hello_world_suite', version='1.0')\n"
            "class HelloWorld:\n"
            "    def physics():\n"
            "        hello_package(adjust=temp_adjust)\n"
            "if __name__ == '__main__':\n"
            "    export_suite(HelloWorld)\n")

        def generate(label, **source):
            tool = ccppMain()
            options_db = tool.default_options_db()
            options_db.update({
                "scheme_files": [f"{h}/hello_scheme.meta", f"{h}/temp_adjust.meta"],
                "host_files": [f"{h}/hello_world_host.meta", f"{h}/hello_world_mod.meta"],
                "kind_map": ["kind_dyn:REAL32"],
                "out": str(tmp_path / label / "out"),
                "tempdir": str(tmp_path / label / "tmp"),
                "verbose": 0, **source})
            result = tool.run(options_db)
            out = options_db["out"]
            return {os.path.basename(p): open(os.path.join(out, p)).read()
                    for p in result.written if p.endswith(".F90")}

        xml = generate("xml", suites=[f"{h}/hello_world_suite.xml"])
        py = generate("py", suites=[], py=str(script))
        assert "hello_world_suite_cap.F90" in xml
        assert py == xml


pkg = ccpp_package("pkg")


@pkg.entry_point
def pkg_step(*, n, hook, empty_hook, slot=scheme_b):
    slot()
    with forLoop(n):
        hook()
        empty_hook()


def host_code():
    scheme_a()
    scheme_c(var_x=1)


@ccpp_suite("s", version="1.0")
class package_suite:
    def physics():
        pkg_step(n=N, hook=host_code, empty_hook=lambda: None, slot=scheme_c)


@ccpp_suite("s", version="1.0")
class package_plain_suite:
    def physics():
        scheme_c()
        with forLoop(N):
            host_code()


class TestPackage:
    def test_entry_point_recorded_with_package(self):
        (step,) = package_suite.groups["physics"]
        assert isinstance(step, CompositeDescriptor)
        assert (step.name, step.package, step.hook) == ("pkg_step", "pkg", False)
        assert pkg.entry_points == {"pkg_step": pkg_step.__wrapped__}

    def test_slot_binding_is_package_code_hook_binding_is_marked(self):
        step = package_suite.groups["physics"][0]
        assert step.items[0] == (scheme_c, {})
        loop = step.items[1]
        assert isinstance(loop, SubcycleDescriptor) and loop.count == N
        (hook,) = loop.schemes
        assert isinstance(hook, CompositeDescriptor)
        assert (hook.name, hook.package, hook.hook) == ("hook", None, True)
        assert hook.items == [(scheme_a, {}), (scheme_c, {"var_x": "1"})]

    def test_ir_properties(self):
        composites = _ops(build_ir(package_suite), CompositeOp)
        assert [(op.composite_name.data,
                 op.package.data if op.package else None,
                 op.hook is not None) for op in composites] == [
            ("pkg_step", "pkg", False), ("hook", None, True)]

    def test_ir_round_trips(self):
        from xdsl.parser import Parser

        text = str(build_ir(package_suite))
        assert str(Parser(make_ccpp_context(), text).parse_module()) == text

    def test_flattened_ir_identical_to_plain_suite(self):
        assert _flattened(package_suite) == str(build_ir(package_plain_suite))

    def test_plain_composite_does_not_mark_hooks(self):
        outer = composite_suite.groups["physics"][0]
        assert outer.package is None
        assert outer.items[1].schemes[1] == (scheme_a, {})

    def test_duplicate_entry_point_rejected(self):
        p = ccpp_package("p")

        @p.entry_point
        def step():
            scheme_a()

        with pytest.raises(ValueError, match="already has an entry point named 'step'"):
            @p.entry_point
            def step():  # noqa: F811
                scheme_b()
