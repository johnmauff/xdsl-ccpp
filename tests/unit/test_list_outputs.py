"""Unit tests for `--list-outputs` (cmake-configure-regen's Part A):
`ccppMain.predict_output_filenames` predicts the set of output filenames a
real `ccppMain.run()` with the same arguments would produce, without
running suite-cap/ccpp-cap codegen or the Fortran/C++ printers.

These exercise each of the 4 naming/gating rules in isolation, using real
example fixture files (paths relative to the repo root, matching
test_ccpp_dsl_run_in_process.py's own convention). The decisive end-to-end
check -- that predicted output matches each of the 20 wired-in examples'
real, freshly-regenerated output byte-for-byte as a filename set, across
all 24 xdsl_ccpp_capgen() calls in their CMakeLists.txt files -- was done
directly against the real CLI (not re-encoded as a test here, since it
needs each example's own scheme/host source trees on disk); all 24 passed.
"""

from xdsl_ccpp.tools.ccpp_dsl import ccppMain


def _options_db(tool, suites, scheme_files, host_files, **overrides):
    options_db = tool.default_options_db()
    options_db.update({
        "suites": suites,
        "scheme_files": scheme_files,
        "host_files": host_files,
        "verbose": 0,
    })
    options_db.update(overrides)
    return options_db


def _predict(options_db):
    tool = ccppMain()
    tool.options_db = tool._normalize_options_db(dict(options_db))
    return tool.predict_output_filenames()


class TestSuiteCapNaming:
    def test_single_suite(self):
        outputs = _predict(_options_db(
            ccppMain(),
            suites=["examples/helloworld/hello_world_suite.xml"],
            scheme_files=[
                "examples/helloworld/hello_scheme.meta",
                "examples/helloworld/temp_adjust.meta",
            ],
            host_files=[
                "examples/helloworld/hello_world_host.meta",
                "examples/helloworld/hello_world_mod.meta",
            ],
        ))
        assert "hello_world_suite_cap.F90" in outputs

    def test_multiple_suites_each_get_their_own_cap(self):
        """examples/capgen's plain (ftn host) call: two suites sharing one
        host, each contributing its own "<name>_cap.F90" -- the suite cap
        name is a pure per-suite XML attribute read, with no interaction
        between suites in the same invocation."""
        outputs = _predict(_options_db(
            ccppMain(),
            suites=[
                "examples/capgen/scheme/ddt_suite.xml",
                "examples/capgen/scheme/temp_suite.xml",
            ],
            scheme_files=[
                "examples/capgen/scheme/make_ddt.meta",
                "examples/capgen/scheme/environ_conditions.meta",
                "examples/capgen/scheme/setup_coeffs.meta",
                "examples/capgen/scheme/temp_set.meta",
                "examples/capgen/scheme/temp_calc_adjust.meta",
                "examples/capgen/scheme/temp_adjust.meta",
            ],
            host_files=[
                "examples/capgen/host_ftn/test_host_data.meta",
                "examples/capgen/host_ftn/test_host_mod.meta",
                "examples/capgen/host_ftn/test_host.meta",
            ],
            host_name="test_host",
        ))
        assert "ddt_suite_cap.F90" in outputs
        assert "temp_suite_cap.F90" in outputs


class TestHostCapNaming:
    def test_derived_from_first_suite_when_host_name_omitted(self):
        outputs = _predict(_options_db(
            ccppMain(),
            suites=["examples/helloworld/hello_world_suite.xml"],
            scheme_files=[
                "examples/helloworld/hello_scheme.meta",
                "examples/helloworld/temp_adjust.meta",
            ],
            host_files=[
                "examples/helloworld/hello_world_host.meta",
                "examples/helloworld/hello_world_mod.meta",
            ],
        ))
        assert "HelloWorld_ccpp_cap.F90" in outputs

    def test_explicit_host_name_overrides_derivation(self):
        outputs = _predict(_options_db(
            ccppMain(),
            suites=[
                "examples/capgen/scheme/ddt_suite.xml",
                "examples/capgen/scheme/temp_suite.xml",
            ],
            scheme_files=[
                "examples/capgen/scheme/make_ddt.meta",
                "examples/capgen/scheme/environ_conditions.meta",
                "examples/capgen/scheme/setup_coeffs.meta",
                "examples/capgen/scheme/temp_set.meta",
                "examples/capgen/scheme/temp_calc_adjust.meta",
                "examples/capgen/scheme/temp_adjust.meta",
            ],
            host_files=[
                "examples/capgen/host_ftn/test_host_data.meta",
                "examples/capgen/host_ftn/test_host_mod.meta",
                "examples/capgen/host_ftn/test_host.meta",
            ],
            host_name="test_host",
        ))
        assert "test_host_ccpp_cap.F90" in outputs
        assert not any("Ddt" in f or "Temp" in f for f in outputs)

    def test_derivation_is_order_dependent_on_the_suites_list(self):
        """When --host-name is omitted, the CamelCase prefix comes from
        the FIRST suite in --suites order, not some canonical/sorted
        choice -- swapping the two suite args' order flips which suite
        "wins" the host cap name (ccpp_cap.py:1219's
        all_suite_names[0], itself XML-parse-order over --suites)."""
        common = dict(
            scheme_files=[
                "examples/capgen/scheme/make_ddt.meta",
                "examples/capgen/scheme/environ_conditions.meta",
                "examples/capgen/scheme/setup_coeffs.meta",
                "examples/capgen/scheme/temp_set.meta",
                "examples/capgen/scheme/temp_calc_adjust.meta",
                "examples/capgen/scheme/temp_adjust.meta",
            ],
            host_files=[
                "examples/capgen/host_ftn/test_host_data.meta",
                "examples/capgen/host_ftn/test_host_mod.meta",
                "examples/capgen/host_ftn/test_host.meta",
            ],
        )
        ddt_first = _predict(_options_db(
            ccppMain(),
            suites=[
                "examples/capgen/scheme/ddt_suite.xml",
                "examples/capgen/scheme/temp_suite.xml",
            ],
            **common,
        ))
        temp_first = _predict(_options_db(
            ccppMain(),
            suites=[
                "examples/capgen/scheme/temp_suite.xml",
                "examples/capgen/scheme/ddt_suite.xml",
            ],
            **common,
        ))
        assert "Ddt_ccpp_cap.F90" in ddt_first
        assert "Temp_ccpp_cap.F90" in temp_first
        assert "Ddt_ccpp_cap.F90" not in temp_first
        assert "Temp_ccpp_cap.F90" not in ddt_first


class TestChostCapGating:
    def test_plain_generation_has_no_bind_c_or_chost_files(self):
        outputs = _predict(_options_db(
            ccppMain(),
            suites=["examples/kessler/scheme/kessler_suite.xml"],
            scheme_files=[
                "examples/kessler/scheme/kessler.meta",
                "examples/kessler/scheme/kessler_update.meta",
            ],
            host_files=[
                "examples/kessler/host_ftn/kessler_host_mod.meta",
                "examples/kessler/host_ftn/kessler_host_sub.meta",
            ],
        ))
        assert not any(f.endswith((".h", ".hpp")) for f in outputs)
        assert "kessler_suite_cap.F90" in outputs
        assert "Kessler_ccpp_cap.F90" in outputs

    def test_explicit_bind_c_flag_adds_main_cap_header_but_no_chost(self):
        """examples/kessler's own BINDC_CAP_DIR call: --bind-c on a host
        with no "language = c++" declaration gets a BIND(C) main cap +
        its .h header, but no separate chost module -- the chost gate
        (cpp_interop.py's CPPInteropCap.apply) checks the real host
        table's own `language` property, not --bind-c."""
        outputs = _predict(_options_db(
            ccppMain(),
            suites=["examples/kessler/scheme/kessler_suite.xml"],
            scheme_files=[
                "examples/kessler/scheme/kessler.meta",
                "examples/kessler/scheme/kessler_update.meta",
            ],
            host_files=[
                "examples/kessler/host_ftn/kessler_host_mod.meta",
                "examples/kessler/host_ftn/kessler_host_sub.meta",
            ],
            bind_c=True,
        ))
        assert "Kessler_ccpp_cap.h" in outputs
        assert not any("chost" in f for f in outputs)

    def test_host_language_cpp_adds_chost_cap_header_and_wrapper(self):
        """examples/capgen's own chost call: no --bind-c passed at all --
        the C++ host's own .meta declares "language = c++", which both
        forces bind_c on for the main cap (ccpp_dsl.py's _host_lang_cpp)
        and triggers the separate chost cap/.h/.hpp triplet."""
        outputs = _predict(_options_db(
            ccppMain(),
            suites=["examples/capgen/scheme/capgen_chost_suite.xml"],
            scheme_files=[
                "examples/capgen/scheme/make_ddt.meta",
                "examples/capgen/scheme/setup_coeffs.meta",
                "examples/capgen/scheme/temp_calc_adjust.meta",
            ],
            host_files=[
                "examples/capgen/host_cpp/capgen_host_mod.meta",
                "examples/capgen/host_cpp/capgen_host_sub.meta",
            ],
        ))
        assert "CapgenChost_ccpp_cap.F90" in outputs
        assert "CapgenChost_ccpp_cap.h" in outputs
        assert "CapgenChost_ccpp_chost_cap.F90" in outputs
        assert "CapgenChost_ccpp_chost_cap.h" in outputs
        assert "CapgenChost_chost.hpp" in outputs


class TestKindsGate:
    def test_kinds_present_for_a_real_example(self):
        """ccpp_kinds.F90/.h is gated on generate-meta-kinds (MetaCAP +
        MetaKind) finding at least one named `real` kind across every
        table -- in practice this is unconditionally True for any real
        invocation, since run_frontend() (and this same prediction code,
        mirroring it) always auto-includes the bundled
        ccpp_constituent_prop_mod.meta, which itself declares
        `kind = kind_phys` real args."""
        outputs = _predict(_options_db(
            ccppMain(),
            suites=["examples/helloworld/hello_world_suite.xml"],
            scheme_files=[
                "examples/helloworld/hello_scheme.meta",
                "examples/helloworld/temp_adjust.meta",
            ],
            host_files=[
                "examples/helloworld/hello_world_host.meta",
                "examples/helloworld/hello_world_mod.meta",
            ],
        ))
        assert "ccpp_kinds.F90" in outputs

    def test_kinds_header_only_emitted_alongside_bind_c(self):
        plain = _predict(_options_db(
            ccppMain(),
            suites=["examples/kessler/scheme/kessler_suite.xml"],
            scheme_files=[
                "examples/kessler/scheme/kessler.meta",
                "examples/kessler/scheme/kessler_update.meta",
            ],
            host_files=[
                "examples/kessler/host_ftn/kessler_host_mod.meta",
                "examples/kessler/host_ftn/kessler_host_sub.meta",
            ],
        ))
        bindc = _predict(_options_db(
            ccppMain(),
            suites=["examples/kessler/scheme/kessler_suite.xml"],
            scheme_files=[
                "examples/kessler/scheme/kessler.meta",
                "examples/kessler/scheme/kessler_update.meta",
            ],
            host_files=[
                "examples/kessler/host_ftn/kessler_host_mod.meta",
                "examples/kessler/host_ftn/kessler_host_sub.meta",
            ],
            bind_c=True,
        ))
        assert "ccpp_kinds.F90" in plain and "ccpp_kinds.h" not in plain
        assert "ccpp_kinds.F90" in bindc and "ccpp_kinds.h" in bindc


class TestUnsupportedModes:
    def test_py_mode_rejected(self):
        tool = ccppMain()
        options_db = tool.default_options_db()
        # Any real file satisfies _normalize_options_db's existence check --
        # predict_output_filenames() must reject --py mode before it would
        # ever try to run this (non-frontend) file as one.
        options_db.update({"py": "xdsl_ccpp/tools/ccpp_dsl.py", "list_outputs": True})
        tool.options_db = tool._normalize_options_db(dict(options_db))
        try:
            tool.predict_output_filenames()
            assert False, "expected CcppDslError"
        except Exception as exc:
            assert "py" in str(exc)
