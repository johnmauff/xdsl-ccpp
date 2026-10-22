"""Lowering packages to package caps (composite-scheme 2f, step 2f-2, IR
stage): synthetic segment schemes, the rewritten suite and the
``ccpp.package_cap`` op (transforms/lower_packages.py)."""

import pytest

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.frontend.py_api import (
    Arg,
    SchemeDescriptor,
    build_ir,
    ccpp_host,
    ccpp_package,
    ccpp_suite,
    forLoop,
)
from xdsl_ccpp.tools.ctx_utils import make_ccpp_context
from xdsl_ccpp.transforms.lower_packages import LowerPackages, interface_args
from xdsl_ccpp.transforms.package_scope import ScopePackages

N = "number_of_diagnostic_subcycles"
_ERR = [Arg("errmsg", standard_name="ccpp_error_message", type="character",
            intent="out", units="none", kind="len=512"),
        Arg("errflg", standard_name="ccpp_error_code", type="integer",
            intent="out", units="1")]


def _arg(name, std, intent, units="K"):
    return Arg(name, standard_name=std, type="real", intent=intent, units=units,
               dimensions=("horizontal_dimension",), kind="kind_phys")


# A package that reads the host's temperature, makes a private work array,
# writes a public output; the hook reads that output.
make = SchemeDescriptor("make", {
    "init": list(_ERR),
    "run": [_arg("t", "air_temperature", "in"), _arg("work", "work_array", "out"), *_ERR]})
use = SchemeDescriptor("use", {
    "run": [_arg("work", "work_array", "in"), _arg("t", "air_temperature", "inout"),
            _arg("tend", "temperature_tendency", "out"), *_ERR]})
diag = SchemeDescriptor("diag", {"run": [_arg("tend", "temperature_tendency", "in"), *_ERR]})


@ccpp_host
class host:
    host = [_arg("t", "air_temperature", "inout")]


pkg = ccpp_package("pkg")


@pkg.entry_point
def step(*, hook):
    make()
    use()
    with forLoop(N):
        hook()


@ccpp_suite("s", version="1.0")
class suite:
    def physics():
        step(hook=diag)


def _lowered(s=suite):
    module = build_ir(s, [host])
    ctx = make_ccpp_context()
    ScopePackages().apply(ctx, module)
    LowerPackages().apply(ctx, module)
    module.verify()
    return module


def _tables(module):
    return {t.table_name.data: t for t in module.walk()
            if isinstance(t, ccpp.TablePropertiesOp)}


def _args(table):
    return {a.standard_name.data: (a.arg_name.data, a.intent.data)
            for a in table.walk() if isinstance(a, ccpp.ArgumentOp)}


class TestLowering:
    def test_suite_calls_segments_and_keeps_hooks(self):
        module = _lowered()
        calls = [o.scheme_name.data for o in module.walk() if isinstance(o, ccpp.SchemeOp)
                 and o.parent_op().name != "ccpp.segment"
                 and not any(p.name == "ccpp.segment" for p in _ancestors(o))]
        # The state schemes bracket the package's entry-point call.
        assert calls == ["pkg_state_create", "step_init_1", "step_1", "diag",
                         "pkg_state_delete"]

    def test_state_schemes_have_one_lifecycle_phase_each(self):
        """<pkg>_state_create has only an _init phase, <pkg>_state_delete only
        a _finalize phase; both take only the error arguments, and stand for
        no package scheme (segment_schemes empty)."""
        tables = _tables(_lowered())
        for name, phase in [("pkg_state_create", "init"), ("pkg_state_delete", "finalize")]:
            table = tables[name]
            assert [t.table_name.data for t in table.walk()
                    if isinstance(t, ccpp.ArgumentTableOp)] == [f"{name}_{phase}"]
            assert set(_args(table)) == {"ccpp_error_message", "ccpp_error_code"}
            assert table.attributes["source_module"].data == "pkg_package_cap"
            assert list(table.attributes["segment_schemes"].data) == []

    def test_synthetic_schemes_point_at_the_package_cap(self):
        tables = _tables(_lowered())
        for name, phase in [("step_init_1", "init"), ("step_1", "run")]:
            table = tables[name]
            assert table.attributes["source_module"].data == "pkg_package_cap"
            assert [t.table_name.data for t in table.walk()
                    if isinstance(t, ccpp.ArgumentTableOp)] == [f"{name}_{phase}"]

    def test_synthetic_schemes_name_their_package_schemes(self):
        """The host's active-scheme list is built from these (CAM-SIMA reads a
        scheme's namelist only if the scheme is listed)."""
        tables = _tables(_lowered())
        assert [s.data for s in tables["step_1"].attributes["segment_schemes"].data] == [
            "make", "use"]
        assert [s.data for s in tables["step_init_1"].attributes["segment_schemes"].data] == [
            "make"]

    def test_interface_excludes_private_names_and_merges_intents(self):
        args = _args(_tables(_lowered())["step_1"])
        assert args == {
            "air_temperature": ("t", "inout"),      # read by make, written by use
            "temperature_tendency": ("tend", "out"),
            "ccpp_error_message": ("errmsg", "out"),
            "ccpp_error_code": ("errflg", "out"),
        }  # work_array is private (pkg__work_array): not in the interface

    def test_package_cap_holds_the_segment_calls(self):
        module = _lowered()
        (cap,) = [o for o in module.walk() if isinstance(o, ccpp.PackageCapOp)]
        segments = {s.segment_name.data: (s.phase.data, s.entry_point.data,
                                          [c.scheme_name.data for c in s.walk()
                                           if isinstance(c, ccpp.SchemeOp)])
                    for s in cap.walk() if isinstance(s, ccpp.SegmentOp)}
        assert segments == {"step_init_1": ("init", "step", ["make"]),
                            "step_1": ("run", "step", ["make", "use"])}

    def test_module_without_packages_unchanged(self):
        @ccpp_suite("s", version="1.0")
        class plain:
            def physics():
                make()
                use()

        module = build_ir(plain)
        before = str(module)
        LowerPackages().apply(make_ccpp_context(), module)
        assert str(module) == before

    def test_ir_round_trips(self):
        from xdsl.parser import Parser

        text = str(_lowered())
        assert str(Parser(make_ccpp_context(), text).parse_module()) == text


def _ancestors(op):
    parent = op.parent_op()
    while parent is not None:
        yield parent
        parent = parent.parent_op()


class TestInterfaceArgs:
    @staticmethod
    def _ops(*args):
        return [ccpp.ArgumentOp(a.name, a.type, a.to_ccpp_attrs()) for a in args]

    def test_intent_rules(self):
        args = interface_args("seg", "run", "pkg", [
            ("a", self._ops(_arg("x", "only_read", "in"), _arg("y", "write_first", "out"),
                            _arg("z", "read_then_write", "in"))),
            ("b", self._ops(_arg("y", "write_first", "in"), _arg("z", "read_then_write", "out"))),
        ])
        assert [(a.standard_name.data, a.intent.data) for a in args] == [
            ("only_read", "in"), ("write_first", "out"), ("read_then_write", "inout")]

    def test_local_name_collision_is_qualified(self):
        args = interface_args("seg", "run", "pkg", [
            ("sw", self._ops(_arg("kdist", "sw_thing", "in"))),
            ("lw", self._ops(_arg("kdist", "lw_thing", "in"))),
        ])
        assert [a.arg_name.data for a in args] == ["kdist", "lw_kdist"]

    def test_device_use_anywhere_makes_argument_device_resident(self):
        on_device = Arg("t", standard_name="air_temperature", type="real", intent="in",
                        units="K", dimensions=("horizontal_dimension",), kind="kind_phys",
                        extra={"memory_space": "device"})
        args = interface_args("seg", "run", "pkg", [
            ("a", self._ops(_arg("t", "air_temperature", "inout"), _arg("x", "host_only", "in"))),
            ("b", self._ops(on_device)),
        ])
        spaces = {a.standard_name.data: a.memory_space for a in args}
        assert spaces["air_temperature"].data == "device"
        assert spaces["host_only"] is None

    def test_disagreeing_units_rejected(self):
        with pytest.raises(ValueError, match="'t' has units|has units 'K' in a but 'degC'"):
            interface_args("seg", "run", "pkg", [
                ("a", self._ops(_arg("t", "air_temperature", "in"))),
                ("b", self._ops(_arg("t", "air_temperature", "in", units="degC"))),
            ])

    def test_private_dimension_rejected(self):
        bad = Arg("b", standard_name="band_values", type="real", intent="in", units="1",
                  dimensions=("pkg__number_of_bands",), kind="kind_phys")
        with pytest.raises(ValueError, match="dimensioned by package-private"):
            interface_args("seg", "run", "pkg", [("a", self._ops(bad))])


def test_rrtmgp_example_lowers(legacy_mode):
    """examples/rrtmgp_composite (host-less): every package segment becomes a
    synthetic scheme, the suite calls no RRTMGP scheme directly any more, and
    the shortwave run segments are the two found by the segmentation."""
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
    module = tool._build_cheap_metadata_module()
    # Host-less, three names CAM declares itself are shared state too
    # (test_package_scope.py::test_rrtmgp_example_scope); declare them.
    from xdsl.dialects.builtin import ArrayAttr, StringAttr

    (package_op,) = [o for o in module.walk() if isinstance(o, ccpp.PackageOp)]
    package_op.properties["shared_state"] = ArrayAttr(list(package_op.shared_state) + [
        StringAttr(n) for n in (
            "longwave_downward_radiative_flux_at_surface_to_coupler",
            "next_calendar_day_to_perform_shortwave_radiation_for_surface_models",
            "tendency_of_dry_air_enthalpy_at_constant_pressure_due_to_longwave_radiation"
            "_adjusted_by_air_pressure_thickness")])
    ctx = make_ccpp_context()
    ScopePackages().apply(ctx, module)
    LowerPackages().apply(ctx, module)
    module.verify()

    segments = {s.segment_name.data: [c.scheme_name.data for c in s.walk()
                                      if isinstance(c, ccpp.SchemeOp)]
                for s in module.walk() if isinstance(s, ccpp.SegmentOp)}
    assert segments["rrtmgp_shortwave_1"] == ["rrtmgp_sw_cloud_optics",
                                              "rrtmgp_sw_mcica_subcol_gen"]
    assert segments["rrtmgp_shortwave_2"][0] == "rrtmgp_sw_gas_optics_pre"
    inner = {name for names in segments.values() for name in names}
    suite_calls = {o.scheme_name.data for o in module.walk()
                   if isinstance(o, ccpp.SchemeOp)
                   and not any(p.name == "ccpp.segment" for p in _ancestors(o))}
    assert not (inner & suite_calls)
    assert {"rrtmgp_shortwave_1", "rrtmgp_shortwave_2", "rrtmgp_cloud_diagnostics"} <= suite_calls
