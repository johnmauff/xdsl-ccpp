"""Package scoping (composite-scheme Stage 2, S2-2, transforms/package_scope.py):
the analysis of which standard names are private to a package (step b) and
the scope-packages pass that renames them and makes them suite-owned (step c)."""

from xdsl_ccpp.frontend.py_api import (
    Arg,
    SchemeDescriptor,
    build_ir,
    ccpp_composite,
    ccpp_host,
    ccpp_package,
    ccpp_suite,
)
from xdsl_ccpp.transforms.package_scope import (
    CONSTITUENT,
    FRAMEWORK,
    FROM_HOST,
    HOST,
    INPUT,
    OUTPUT,
    SHARED,
    SHARED_STATE,
    SUITE,
    CallSite,
    format_package_scopes,
    package_scopes,
)


def _arg(name, std, intent, dims=()):
    return Arg(name, standard_name=std, type="real", intent=intent,
               units="none", dimensions=dims, kind="kind_phys")


_err = [Arg("errmsg", standard_name="ccpp_error_message", type="character",
            intent="out", units="none", kind="len=512"),
        Arg("errflg", standard_name="ccpp_error_code", type="integer",
            intent="out", units="1")]

# Two package schemes using the same local name for different private
# objects (RRTMGP's kdist), one dimensioned by a package-private extent.
sw_setup = SchemeDescriptor("sw_setup", {"init": [
    _arg("kdist", "sw_object", "out"),
    Arg("nband", standard_name="number_of_sw_bands", type="integer",
        intent="out", units="count"), *_err]})
lw_setup = SchemeDescriptor("lw_setup", {"init": [
    _arg("kdist", "lw_object", "out"), *_err]})
sw_optics = SchemeDescriptor("sw_optics", {"run": [
    _arg("kdist", "sw_object", "inout"),
    _arg("band_tau", "sw_band_optical_depth", "out", ("number_of_sw_bands",)),
    _arg("t", "air_temperature", "in", ("horizontal_dimension",)),
    _arg("q", "water_vapor", "in", ("horizontal_dimension",)),
    _arg("coef", "package_coefficient", "in"),
    _arg("flux", "sw_flux", "out"), *_err]})
for _a in sw_optics.entry_points["run"]:
    if _a.standard_name == "water_vapor":
        _a.extra["advected"] = True
lw_optics = SchemeDescriptor("lw_optics", {"run": [
    _arg("kdist", "lw_object", "in"), _arg("q", "lw_heating", "out"), *_err]})
# Host code: the hook reads the package's flux; the suite scheme frees the
# LW object.
diagnostics = SchemeDescriptor("diagnostics", {"run": [
    _arg("flux", "sw_flux", "in"), *_err]})
post = SchemeDescriptor("post", {"run": [_arg("kdist", "lw_object", "inout"), *_err]})


@ccpp_host
class host:
    host = [_arg("t", "air_temperature", "inout", ("horizontal_dimension",))]


rad = ccpp_package("rad", shared_state=["lw_object"])


@rad.entry_point
def rad_init():
    sw_setup()
    lw_setup()


@rad.entry_point
def rad_sw(*, diag):
    sw_optics()
    diag()


@rad.entry_point
def rad_lw():
    lw_optics()


@ccpp_suite("s", version="1.0")
class suite:
    def physics():
        rad_init()
        rad_sw(diag=diagnostics)
        rad_lw()
        post()


def _scopes(s=suite):
    return package_scopes(build_ir(s, [host]))


class TestPackageScope:
    def test_private_names_and_their_local_names(self):
        rad = _scopes()["rad"]
        assert rad.private == {
            "sw_object": {"kdist"},
            "number_of_sw_bands": {"nband"},
            "sw_band_optical_depth": {"band_tau"},
            "lw_heating": {"q"},
        }

    def test_public_reasons(self):
        rad = _scopes()["rad"]
        assert rad.public == {
            "air_temperature": HOST,
            "water_vapor": CONSTITUENT,
            "package_coefficient": INPUT,
            "sw_flux": SHARED,
            "lw_object": SHARED,
            "ccpp_error_message": FRAMEWORK,
            "ccpp_error_code": FRAMEWORK,
            "horizontal_dimension": HOST,
        }

    def test_shared_names_record_hook_and_suite_users(self):
        rad = _scopes()["rad"]
        assert rad.shared_with == {
            "sw_flux": {CallSite("diagnostics", SUITE, ("rad_sw", "diag"))},
            "lw_object": {CallSite("post", SUITE)},
        }

    def test_interface_directions(self):
        rad = _scopes()["rad"]
        assert rad.direction == {"sw_flux": OUTPUT, "lw_object": SHARED_STATE}
        assert rad.declared_shared_state == ["lw_object"]
        assert rad.interface_problems() == ([], [])

    def test_input_direction(self):
        source = SchemeDescriptor("source", {"run": [_arg("x", "host_flag", "out"), *_err]})
        reader = SchemeDescriptor("reader", {"run": [_arg("x", "host_flag", "in"), *_err]})
        pkg = ccpp_package("pkg")

        @pkg.entry_point
        def step(*, fill):
            fill()
            reader()

        @ccpp_suite("s", version="1.0")
        class s:
            def physics():
                step(fill=source)

        assert _scopes(s)["pkg"].direction == {"host_flag": FROM_HOST}

    def test_undeclared_and_stale_shared_state(self):
        pkg = ccpp_package("pkg", shared_state=["sw_object", "nothing_here"])

        @pkg.entry_point
        def step():
            lw_setup()
            sw_setup()

        @ccpp_suite("s", version="1.0")
        class s:
            def physics():
                step()
                post()

        errors, warnings = _scopes(s)["pkg"].interface_problems()
        assert errors == [
            "Package 'pkg': 'lw_object' is written both by the package and by "
            "host code (post [suite]) but is not declared in its shared_state."]
        assert warnings == [
            "Package 'pkg': shared_state lists 'nothing_here', which is not shared "
            "state (the package does not touch it); remove it from the list.",
            "Package 'pkg': shared_state lists 'sw_object', which is not shared "
            "state (it is private); remove it from the list."]
        report = format_package_scopes(_scopes(s))
        assert "  ERROR: Package 'pkg': 'lw_object'" in report
        assert "  WARNING: Package 'pkg': shared_state lists 'nothing_here'" in report

    def test_slot_code_is_package_code(self):
        """A scheme bound to a slot (a defaulted parameter) is package code
        even when the host supplies it."""
        pkg = ccpp_package("pkg")

        @pkg.entry_point
        def step(*, reader=diagnostics):
            sw_optics()
            reader()

        @ccpp_suite("s", version="1.0")
        class s:
            def physics():
                step(reader=diagnostics)

        assert "sw_flux" in _scopes(s)["pkg"].private

    def test_anonymous_composite_and_suite_code_have_no_package(self):
        @ccpp_composite
        def block():
            sw_setup()
            sw_optics()

        @ccpp_suite("s", version="1.0")
        class s:
            def physics():
                block()

        assert _scopes(s) == {}
        assert format_package_scopes({}).startswith("No packages")

    def test_report(self):
        report = format_package_scopes(_scopes())
        assert report.splitlines()[0] == (
            "package rad: 12 standard names, 4 private, 8 public")
        assert "    sw_object  (kdist)" in report
        assert ("    sw_flux  <- diagnostics [hook rad_sw.diag]" in report)
        assert "    lw_object  <- post [suite]" in report


def test_rrtmgp_example_scope(legacy_mode, capsys):
    """examples/rrtmgp_composite, host-less: both k-distribution objects
    (local name ``kdist`` in the SW and LW gas-optics schemes) are private to
    the package, while the objects rrtmgp_post frees and the fluxes the
    diagnostics hooks read stay public."""
    import glob

    from xdsl_ccpp.tools.ccpp_dsl import ccppMain

    d = "examples/rrtmgp_composite"
    tool = ccppMain()
    options_db = tool.default_options_db()
    options_db.update({
        "suites": [], "py": f"{d}/suite_rrtmgp_composite_py.py",
        "scheme_files": sorted(f for f in glob.glob(f"{d}/meta/**/*.meta", recursive=True)
                               if "/objects/" not in f),
        "host_files": [], "legacy_mode": True, "verbose": 0,
        "list_package_scope": True})
    tool.run(options_db)
    report = capsys.readouterr().out
    assert report.startswith("package rrtmgp: ")

    tool.options_db = tool._normalize_options_db(dict(options_db))
    rrtmgp = package_scopes(tool._build_cheap_metadata_module())["rrtmgp"]
    for kind in ("shortwave", "longwave"):
        assert "kdist" in rrtmgp.private[f"{kind}_gas_optics_object_for_rrtmgp"]
        assert rrtmgp.public[f"{kind}_all_sky_flux_object_for_rrtmgp"] == SHARED
        assert CallSite("rrtmgp_post", SUITE) in rrtmgp.shared_with[
            f"{kind}_atmosphere_optical_properties_object_for_rrtmgp"]
    assert CallSite("rrtmgp_sw_diagnostics", SUITE, ("rrtmgp_shortwave", "diagnostics")) \
        in rrtmgp.shared_with["shortwave_net_radiative_flux"]
    # Every declared shared-state name really is shared state.  Without CAM's
    # host metadata, three names CAM itself declares (coupler fields, the
    # heating carried between radiation steps) are reported as undeclared
    # shared state too; with it, the package's interface check is clean.
    errors, warnings = rrtmgp.interface_problems()
    assert warnings == []
    assert sorted(e.split("'")[3] for e in errors) == [
        "longwave_downward_radiative_flux_at_surface_to_coupler",
        "next_calendar_day_to_perform_shortwave_radiation_for_surface_models",
        "tendency_of_dry_air_enthalpy_at_constant_pressure_due_to_longwave_radiation"
        "_adjusted_by_air_pressure_thickness"]


class TestScopePackagesPass:
    @staticmethod
    def _scoped(s=suite):
        from xdsl_ccpp.tools.ctx_utils import make_ccpp_context
        from xdsl_ccpp.transforms.package_scope import ScopePackages

        module = build_ir(s, [host])
        ScopePackages().apply(make_ccpp_context(), module)
        return module

    @staticmethod
    def _args(module):
        from xdsl_ccpp.dialects import ccpp
        from xdsl_ccpp.dialects.ccpp import TableTypeKind
        from xdsl_ccpp.transforms.util.cap_shared import iter_arg_tables

        return {(t.table_name.data, a.arg_name.data): a
                for _, t in iter_arg_tables(module, table_type=TableTypeKind.Scheme)
                for a in t.body.ops if isinstance(a, ccpp.ArgumentOp)}

    def test_private_names_renamed_and_suite_owned(self):
        args = self._args(self._scoped())
        sw, lw = args[("sw_setup_init", "kdist")], args[("lw_setup_init", "kdist")]
        assert sw.standard_name.data == "rad__sw_object"
        assert args[("sw_optics_run", "kdist")].standard_name.data == "rad__sw_object"
        assert lw.standard_name.data == "lw_object"  # public: post frees it
        assert sw.is_interstitial is not None

    def test_private_dimension_renamed(self):
        tau = self._args(self._scoped())[("sw_optics_run", "band_tau")]
        assert tau.standard_name.data == "rad__sw_band_optical_depth"
        assert tau.dim_names.data == "rad__number_of_sw_bands"

    def test_public_names_untouched(self):
        args = self._args(self._scoped())
        for key, std in [(("lw_setup_init", "kdist"), "lw_object"),
                         (("sw_optics_run", "flux"), "sw_flux"),
                         (("sw_optics_run", "t"), "air_temperature"),
                         (("sw_optics_run", "coef"), "package_coefficient")]:
            assert args[key].standard_name.data == std
            assert args[key].is_interstitial is None
        assert args[("sw_optics_run", "t")].dim_names.data == "horizontal_dimension"

    def test_undeclared_shared_state_is_an_error(self, capsys):
        import pytest

        from xdsl_ccpp.tools.ctx_utils import make_ccpp_context
        from xdsl_ccpp.transforms.package_scope import ScopePackages

        pkg = ccpp_package("pkg", shared_state=["nothing_here"])

        @pkg.entry_point
        def step():
            lw_setup()

        @ccpp_suite("s", version="1.0")
        class s:
            def physics():
                step()
                post()

        with pytest.raises(ValueError, match="'lw_object' is written both"):
            ScopePackages().apply(make_ccpp_context(), build_ir(s, [host]))
        assert "shared_state lists 'nothing_here'" in capsys.readouterr().err

    def test_init_may_only_call_init_only_schemes(self):
        from xdsl_ccpp.transforms.package_scope import init_problems

        pkg = ccpp_package("pkg", shared_state=["lw_object"])

        @pkg.entry_point
        def step():
            lw_setup()
            lw_optics()

        @pkg.init
        def pkg_setup():
            sw_setup()
            sw_optics()

        @ccpp_suite("s", version="1.0")
        class s:
            def physics():
                step()
                post()

        module = build_ir(s, [host])
        assert init_problems(module) == [
            "Package 'pkg': init 'pkg_setup' calls 'sw_optics', which has phase(s) "
            "run; a package init may only call schemes with register, init or "
            "final phases."]
        # The init's schemes are package code: sw_setup's object is private.
        assert "sw_object" in package_scopes(module)["pkg"].private

    def test_module_without_packages_unchanged(self):
        from xdsl_ccpp.tools.ctx_utils import make_ccpp_context
        from xdsl_ccpp.transforms.package_scope import ScopePackages

        module = build_ir(package_free_suite, [host])
        before = str(module)
        ScopePackages().apply(make_ccpp_context(), module)
        assert str(module) == before


@ccpp_suite("s", version="1.0")
class package_free_suite:
    def physics():
        sw_setup()
        sw_optics()


_META = """\
[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_{phase}
  type = scheme
[ kdist ]
  standard_name = {std}
  units = none
  dimensions = ()
  type = real
  kind = kind_phys
  intent = {intent}
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

_HOSTLESS_SUITE = """\
from xdsl_ccpp.frontend.py_api import (ccpp_package, ccpp_scheme_ref, ccpp_suite,
                                       export_suite)

sw_setup, sw_use, lw_setup, lw_use = (ccpp_scheme_ref(n) for n in
                                      ("sw_setup", "sw_use", "lw_setup", "lw_use"))
rad = ccpp_package("rad")

@rad.entry_point
def rad_init():
    sw_setup()
    lw_setup()

@rad.entry_point
def rad_run():
    sw_use()
    lw_use()

@ccpp_suite("rad_suite", version="1.0")
class RadSuite:
    def setup():
        rad_init()
    def physics():
        rad_run()

if __name__ == "__main__":
    export_suite(RadSuite)
"""


def test_hostless_local_name_collision_resolved_by_scoping(tmp_path, capfd):
    """Two private objects with the same local name (RRTMGP's SW and LW
    ``kdist``), no host metadata: without scoping both are caller-supplied
    suite dummy arguments and collide; with scoping they are suite-owned, the
    suite cap generates, and each gets its own variable."""
    import pytest

    from xdsl_ccpp.tools.ccpp_dsl import ccppMain

    schemes = []
    for name, phase, std, intent in [("sw_setup", "init", "sw_object", "out"),
                                     ("sw_use", "run", "sw_object", "in"),
                                     ("lw_setup", "init", "lw_object", "out"),
                                     ("lw_use", "run", "lw_object", "in")]:
        path = tmp_path / f"{name}.meta"
        path.write_text(_META.format(name=name, phase=phase, std=std, intent=intent))
        schemes.append(str(path))
    script = tmp_path / "rad_suite.py"
    script.write_text(_HOSTLESS_SUITE)

    def generate(label, scoped):
        tool = ccppMain()
        if not scoped:
            build = tool._build_pipeline
            tool._build_pipeline = lambda: build().replace("scope-packages,", "")
        options_db = tool.default_options_db()
        options_db.update({"suites": [], "py": str(script), "scheme_files": schemes,
                           "host_files": [], "out": str(tmp_path / label),
                           "tempdir": str(tmp_path / label / "tmp"), "verbose": 0})
        tool.run(options_db)
        return (tmp_path / label / "rad_suite_cap.F90").read_text()

    from xdsl_ccpp.tools.ccpp_dsl import CcppDslError

    with pytest.raises(CcppDslError):
        generate("unscoped", scoped=False)
    assert "name collision on 'kdist'" in capfd.readouterr().err
    cap = generate("scoped", scoped=True)
    decls = [line.strip() for line in cap.splitlines()
             if "kdist" in line and "::" in line]
    assert sorted(decls) == ["real(kind=kind_phys) :: lw_setup_kdist",
                             "real(kind=kind_phys) :: sw_setup_kdist"]
