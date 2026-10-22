"""Package segmentation (composite-scheme 2f, step 2f-1): how a per-package
cap would cut package code into routines (transforms/package_segments.py)."""

import pytest

from xdsl_ccpp.frontend.py_api import (
    Arg,
    SchemeDescriptor,
    build_ir,
    ccpp_composite,
    ccpp_host,
    ccpp_package,
    ccpp_suite,
    forLoop,
)
from xdsl_ccpp.transforms.package_segments import (
    EntryCall,
    HostCall,
    Loop,
    Segment,
    format_package_segments,
    multi_instance_problems,
    package_segments,
)

_ERR = [Arg("errmsg", standard_name="ccpp_error_message", type="character",
            intent="out", units="none", kind="len=512"),
        Arg("errflg", standard_name="ccpp_error_code", type="integer",
            intent="out", units="1")]


def _scheme(name, *phases):
    return SchemeDescriptor(name, {phase: list(_ERR) for phase in phases})


p1 = _scheme("p1", "init", "run")
p2 = _scheme("p2", "run")
p3 = _scheme("p3", "init", "run", "final")
h1 = _scheme("h1", "init", "run")
h2 = _scheme("h2", "run")            # no init phase: does not split init segments
N = "number_of_diagnostic_subcycles"

pkg = ccpp_package("pkg")


@pkg.entry_point
def step(*, hook):
    p1()
    hook()
    with forLoop(N):                 # all package code: stays in the segment
        p2()
    p3()


@pkg.entry_point
def looped(*, hook):
    with forLoop(N):                 # contains a hook: stays in the suite cap
        p1()
        hook()
        p2()


def _run(suite, phase="run", group="physics"):
    return package_segments(build_ir(suite))["s"][group][phase]


def _entry(name, call=1):
    return EntryCall("pkg", name, call)


class TestRunPhase:
    def test_hook_splits_entry_point_and_package_loop_stays_in_segment(self):
        @ccpp_suite("s", version="1.0")
        class s:
            def physics():
                h1()
                step(hook=h2)

        assert _run(s) == [
            HostCall("h1"),
            Segment(_entry("step"), 1, ["p1"]),
            HostCall("h2", ("step", "hook")),
            Segment(_entry("step"), 2, [Loop(N, ["p2"]), "p3"]),
        ]

    def test_loop_with_hook_stays_in_suite_cap(self):
        @ccpp_suite("s", version="1.0")
        class s:
            def physics():
                looped(hook=h2)

        assert _run(s) == [Loop(N, [
            Segment(_entry("looped"), 1, ["p1"]),
            HostCall("h2", ("looped", "hook")),
            Segment(_entry("looped"), 2, ["p2"]),
        ])]

    def test_consecutive_entry_points_are_separate_segments(self):
        @ccpp_suite("s", version="1.0")
        class s:
            def physics():
                step(hook=h2)
                step(hook=h2)

        nodes = _run(s)
        names = [n.name("run") for n in nodes if isinstance(n, Segment)]
        assert names == ["step_1", "step_2", "step_c2_1", "step_c2_2"]

    def test_anonymous_composite_is_transparent(self):
        @ccpp_composite
        def block():
            h1()

        @ccpp_suite("s", version="1.0")
        class s:
            def physics():
                block()
                step(hook=block)

        assert _run(s)[0] == HostCall("h1")
        assert _run(s)[2] == HostCall("h1", ("step", "hook"))

    def test_suite_without_packages_has_no_segments(self):
        @ccpp_suite("s", version="1.0")
        class s:
            def physics():
                h1()

        assert package_segments(build_ir(s)) == {}


class TestOtherPhases:
    def test_init_segments_follow_scheme_phases_and_flatten_loops(self):
        @ccpp_suite("s", version="1.0")
        class s:
            def physics():
                looped(hook=h1)          # h1 has init: splits looped's init calls
                step(hook=h2)            # h2 has no init: p1 and p3 stay together

        assert _run(s, "init") == [
            Segment(_entry("looped"), 1, ["p1"]),
            HostCall("h1", ("looped", "hook")),
            Segment(_entry("step"), 1, ["p1", "p3"]),
        ]
        assert [n.name("init") for n in _run(s, "init") if isinstance(n, Segment)] == [
            "looped_init_1", "step_init_1"]
        assert _run(s, "final") == [Segment(_entry("step"), 1, ["p3"])]

    def test_package_init_is_its_own_segment(self):
        q = ccpp_package("q")

        @q.entry_point
        def q_step():
            p2()

        @q.init
        def q_setup():
            p1()

        @ccpp_suite("s", version="1.0")
        class s:
            def physics():
                q_step()
                h1()

        nodes = package_segments(build_ir(s))["s"]["physics"]["init"]
        assert nodes == [Segment(EntryCall("q", "q_setup", 1), 1, ["p1"]), HostCall("h1")]


class TestMultiInstance:
    @staticmethod
    def _host(*std_names):
        @ccpp_host
        class host:
            host = [Arg(n, standard_name=n, type="integer", units="1") for n in std_names]
        return host

    @ccpp_suite("s", version="1.0")
    class pkg_suite:
        def physics():
            step(hook=h2)

    def test_multi_instance_host_is_rejected(self):
        module = build_ir(self.pkg_suite,
                          [self._host("instance_number", "number_of_instances")])
        (problem,) = multi_instance_problems(module)
        assert "Package(s) pkg used with a multi-instance host" in problem

    def test_one_instance_name_alone_is_not_multi_instance(self):
        module = build_ir(self.pkg_suite, [self._host("instance_number")])
        assert multi_instance_problems(module) == []

    def test_scope_packages_stops_on_multi_instance(self):
        from xdsl_ccpp.tools.ctx_utils import make_ccpp_context
        from xdsl_ccpp.transforms.package_scope import ScopePackages

        module = build_ir(self.pkg_suite,
                          [self._host("instance_number", "number_of_instances")])
        with pytest.raises(ValueError, match="multi-instance host"):
            ScopePackages().apply(make_ccpp_context(), module)


def test_report_format():
    @ccpp_suite("s", version="1.0")
    class s:
        def physics():
            looped(hook=h2)

    assert format_package_segments(package_segments(build_ir(s))).splitlines() == [
        "segments: suite s, group physics, phase init",
        "  segment looped_init_1: p1",
        "segments: suite s, group physics, phase run",
        f"  loop {N}:",
        "    segment looped_1: p1",
        "    host    h2 [hook looped.hook]",
        "    segment looped_2: p2",
    ]


def test_rrtmgp_example_segments(legacy_mode):
    """examples/rrtmgp_composite: the shortwave entry point becomes 2 run
    segments -- cloud optics + McICA, then the gas-optics-to-heating-rate
    chain inside the diagnostic loop (solar_irradiance_data has no run phase,
    so it does not split it) -- with the loop itself in the suite cap."""
    import glob

    from xdsl_ccpp.tools.ccpp_dsl import ccppMain

    d = "examples/rrtmgp_composite"
    tool = ccppMain()
    options_db = tool.default_options_db()
    options_db.update({
        "suites": [], "py": f"{d}/suite_rrtmgp_composite_py.py",
        "scheme_files": sorted(f for f in glob.glob(f"{d}/meta/**/*.meta", recursive=True)
                               if "/objects/" not in f),
        "host_files": [], "legacy_mode": True, "verbose": 0})
    tool.options_db = tool._normalize_options_db(dict(options_db))
    run = package_segments(tool._build_cheap_metadata_module())[
        "rrtmgp"]["physics_after_coupler"]["run"]

    def sw(nodes):
        for node in nodes:
            if isinstance(node, Segment) and node.entry.entry_point == "rrtmgp_shortwave":
                yield node
            elif isinstance(node, Loop):
                yield from sw(node.body)

    first, second = sw(run)
    assert first.body == ["rrtmgp_sw_cloud_optics", "rrtmgp_sw_mcica_subcol_gen"]
    assert second.body == [
        "rrtmgp_sw_gas_optics_pre", "rrtmgp_sw_gas_optics", "rrtmgp_sw_solar_var",
        "rrtmgp_sw_aerosols", "rrtmgp_sw_rte", "rrtmgp_sw_calculate_fluxes",
        "rrtmgp_sw_calculate_heating_rate"]
    loops = [n for n in run if isinstance(n, Loop)]
    assert len(loops) == 2 and second in loops[0].body
