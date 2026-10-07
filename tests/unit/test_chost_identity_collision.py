"""Unit tests for cpp_interop.py's chost-identity-collision/
chost-dim-collision fix: _chost_scan_scheme_phase_args /
_chost_resolve_scheme_arg_identities.

Mirrors test_run_dispatch_host_wrapper_resolution.py's own proven
bare-name-collision tests (the already-fixed run_dispatch.py analog,
chost-rank3-bindc's PR #112 review) -- same var_compat-shaped
"scalar_var" collision (effr_pre/effr_post/effr_diag all reusing it),
applied to cpp_interop.py's own local_to_std/local_to_dim_names maps
instead of run_dispatch.py's local_to_host_info.

Before this fix, `_chost_build_maps`'s `local_to_std` scanned ALL of
meta_data globally (every scheme, every table, no phase/scheme scoping,
no collision handling) -- these tests exercise the two new functions
that replaced that flat scan: a per-suite-fn-group scoped scan
(_chost_scan_scheme_phase_args) feeding a pure, collision-aware resolve
step (_chost_resolve_scheme_arg_identities).
"""

from xdsl_ccpp.dialects.ccpp import ArgOwnershipKind
from xdsl_ccpp.transforms.cpp_interop import (
    _chost_resolve_scheme_arg_identities,
    _chost_scan_scheme_phase_args,
    _chost_scheme_phase_suffixes,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    CCPPArgument,
    CCPPArgumentTable,
    CCPPTableProperties,
)

# ---------------------------------------------------------------------------
# Helpers (same convention as test_run_dispatch_host_wrapper_resolution.py)
# ---------------------------------------------------------------------------


def _make_arg(name, **attrs):
    arg = CCPPArgument(name)
    for k, v in attrs.items():
        arg.setAttr(k, v)
    return arg


def _make_arg_table(name, args, table_type):
    tbl = CCPPArgumentTable()
    tbl.setAttr("name", name)
    tbl.setAttr("type", table_type)
    for arg in args:
        tbl.setFunctionArgument(arg)
    return tbl


def _make_scheme_props(scheme_name, args, phase_suffix="_run"):
    props = CCPPTableProperties()
    props.setAttr("name", scheme_name)
    props.setAttr("type", "scheme")
    props.arg_tables[scheme_name + phase_suffix] = _make_arg_table(
        scheme_name + phase_suffix, args, "scheme"
    )
    return props


# ---------------------------------------------------------------------------
# chost-identity-collision: bare-name collision across three or more schemes
# ---------------------------------------------------------------------------


class TestBareNameCollisionAcrossSchemes:
    """Three schemes each declare their own arg literally named "x" for
    three distinct standard_names, mirroring var_compat's own
    effr_pre/effr_post/effr_diag all reusing "scalar_var". Before this
    fix, cpp_interop.py's flat, unscoped local_to_std would have kept
    only the first-seen mapping (std_a) for EVERY one of these three
    args -- silently misclassifying scheme_b's and scheme_c's own args
    under scheme_a's standard_name entirely, not just mis-shaping them.
    """

    def _meta_data(self):
        return {
            "scheme_a": _make_scheme_props("scheme_a", [
                _make_arg("x", standard_name="std_a", model_var_name="host_a"),
            ]),
            "scheme_b": _make_scheme_props("scheme_b", [
                _make_arg("x", standard_name="std_b", model_var_name="x"),
            ]),
            "scheme_c": _make_scheme_props("scheme_c", [
                _make_arg("x", standard_name="std_c", model_var_name="host_c"),
            ]),
        }

    def test_each_sibling_resolves_to_its_own_std_name(self):
        by_bare = _chost_scan_scheme_phase_args(
            ["scheme_a", "scheme_b", "scheme_c"], self._meta_data(), ("_run",),
        )
        local_to_std, _ = _chost_resolve_scheme_arg_identities(by_bare)
        # scheme_a and scheme_c's dummy args were renamed by suite_cap.py's
        # own _build_block_and_name_hints to their model_var_name; scheme_b
        # keeps "x" unchanged since its model_var_name already equals its
        # bare name -- local_to_std's own keys must match exactly.
        assert local_to_std["host_a"] == "std_a"
        assert local_to_std["x"] == "std_b"
        assert local_to_std["host_c"] == "std_c"
        # OLD bug: local_to_std["x"] would have been "std_a" (first-seen,
        # global, un-renamed) -- scheme_b/scheme_c's own args would have
        # resolved under the wrong standard_name entirely.

    def test_order_independent(self):
        """The fix must not depend on which colliding scheme is scanned
        first -- reversing scheme_names must give the same result."""
        by_bare = _chost_scan_scheme_phase_args(
            ["scheme_c", "scheme_b", "scheme_a"], self._meta_data(), ("_run",),
        )
        local_to_std, _ = _chost_resolve_scheme_arg_identities(by_bare)
        assert local_to_std["host_a"] == "std_a"
        assert local_to_std["x"] == "std_b"
        assert local_to_std["host_c"] == "std_c"


class TestRepeatedIdenticalMatchIsNotACollision:
    """Two schemes independently declare their own arg literally named
    "ncol", both mapped to the SAME standard_name and the SAME
    model_var_name (var_compat's real "ncol" -> "ncols" case). This must
    resolve via the plain bare-name key, exactly as before -- deduping by
    standard_name (not raw fn_arg occurrence count) is what keeps this
    from being miscounted as a collision."""

    def _meta_data(self):
        return {
            "scheme_a": _make_scheme_props("scheme_a", [
                _make_arg("ncol", standard_name="horizontal_dimension", model_var_name="ncols"),
            ]),
            "scheme_b": _make_scheme_props("scheme_b", [
                _make_arg("ncol", standard_name="horizontal_dimension", model_var_name="ncols"),
            ]),
        }

    def test_resolves_via_bare_name(self):
        by_bare = _chost_scan_scheme_phase_args(
            ["scheme_a", "scheme_b"], self._meta_data(), ("_run",),
        )
        local_to_std, _ = _chost_resolve_scheme_arg_identities(by_bare)
        assert local_to_std == {"ncol": "horizontal_dimension"}


# ---------------------------------------------------------------------------
# chost-dim-collision: dim_names must follow the identical collision-
# resolution keys as local_to_std for the same colliding bare name
# ---------------------------------------------------------------------------


class TestDimNamesFollowSameKeys:
    """A colliding array argument's dim_names must be keyed identically
    to its own local_to_std entry -- before this fix, cpp_interop.py's
    separate, equally-unscoped local_to_dim_names loop had the exact
    same bug, independently."""

    def _meta_data(self):
        return {
            "scheme_a": _make_scheme_props("scheme_a", [
                _make_arg(
                    "flux", standard_name="flux_a", model_var_name="host_flux_a",
                    dim_names=["horizontal_dimension", "vertical_layer_dimension"],
                ),
            ]),
            "scheme_b": _make_scheme_props("scheme_b", [
                _make_arg(
                    "flux", standard_name="flux_b", model_var_name="flux",
                    dim_names=["horizontal_dimension"],
                ),
            ]),
        }

    def test_dim_names_keyed_identically_to_local_to_std(self):
        by_bare = _chost_scan_scheme_phase_args(
            ["scheme_a", "scheme_b"], self._meta_data(), ("_run",),
        )
        local_to_std, local_to_dim_names = _chost_resolve_scheme_arg_identities(by_bare)
        assert local_to_std["host_flux_a"] == "flux_a"
        assert local_to_std["flux"] == "flux_b"
        assert local_to_dim_names["host_flux_a"] == [
            "horizontal_dimension", "vertical_layer_dimension",
        ]
        assert local_to_dim_names["flux"] == ["horizontal_dimension"]
        # OLD bug: local_to_dim_names["flux"] would have been scheme_a's own
        # 2-dimension list (first-seen, global) -- scheme_b's real rank-1
        # array would have been given a bogus second dimension expression.


# ---------------------------------------------------------------------------
# Scoping itself is what prevents a cross-group collision from ever being
# seen in the first place -- the actual mechanism the fix relies on, not
# just the resolve step's own correctness in isolation.
# ---------------------------------------------------------------------------


class TestScopingPreventsCrossGroupCollision:
    """scheme_a (this suite-fn's own group) and scheme_d (a DIFFERENT
    suite-fn's group, not in scope here) both declare "x" for different
    standard_names. Once scheme_names passed in is correctly scoped to
    just scheme_a's own group, scheme_d's reused name must never even be
    seen as a collision -- confirming the fix's real mechanism (scoping
    the scan to the right schemes) rather than relying solely on
    model_var_name-based resolution to paper over an overly-broad scan.
    """

    def _meta_data(self):
        return {
            "scheme_a": _make_scheme_props("scheme_a", [
                _make_arg("x", standard_name="std_a", model_var_name="host_a"),
            ]),
            # Deliberately NOT host-matched (no model_var_name) -- models
            # the "unresolvable collision member" case that can't actually
            # occur in a real build (suite_cap.py's own
            # _build_block_and_name_hints would already have hard-errored
            # first), used here only to exercise the defensive skip.
            "scheme_d": _make_scheme_props("scheme_d", [
                _make_arg("x", standard_name="std_d"),
            ]),
        }

    def test_scoped_to_one_group_sees_no_collision(self):
        by_bare = _chost_scan_scheme_phase_args(
            ["scheme_a"], self._meta_data(), ("_run",),
        )
        local_to_std, _ = _chost_resolve_scheme_arg_identities(by_bare)
        assert local_to_std == {"x": "std_a"}

    def test_both_groups_together_would_collide(self):
        """Confirms the scoping in the test above is actually doing
        something -- scanning both schemes together DOES produce a
        genuine collision: scheme_a's own entry resolves via its
        model_var_name ("host_a"), while scheme_d's entry (no
        model_var_name) is defensively skipped rather than mis-keyed."""
        by_bare = _chost_scan_scheme_phase_args(
            ["scheme_a", "scheme_d"], self._meta_data(), ("_run",),
        )
        local_to_std, _ = _chost_resolve_scheme_arg_identities(by_bare)
        assert local_to_std == {"host_a": "std_a"}


# ---------------------------------------------------------------------------
# Copilot PR #113 review, finding 1: an excluded scheme arg (SuiteOwned, or
# a scalar intent(out) value) must never participate in collision detection
# at all -- suite_cap.py's own input_arg_list (suite_cap.py:2341-2357)
# never includes either, so a bare name shared between one of these and a
# real surviving input is NOT a real collision from suite_cap.py's own
# point of view, even though a naive unfiltered scan would see 2 entries.
# ---------------------------------------------------------------------------


class TestSuiteOwnedArgExcludedFromCollisionDetection:
    """scheme_a's "x" is SuiteOwned (becomes a module-level variable, never
    a suite-cap dummy argument at all); scheme_b's "x" is a real surviving
    input. Before the Copilot PR #113 fix, the raw scan would have seen 2
    entries for bare name "x" and (wrongly) treated this as a real
    collision, keying scheme_b's own real input by its model_var_name even
    though suite_cap.py itself never renamed it (no collision from its own
    point of view, since the SuiteOwned entry was excluded before its own
    collision detection ever ran) -- causing the real lookup (still under
    the plain bare name "x") to miss entirely."""

    def _meta_data(self):
        return {
            "scheme_a": _make_scheme_props("scheme_a", [
                _make_arg(
                    "x", standard_name="suite_owned_std", model_var_name="host_a",
                    ownership_kind=ArgOwnershipKind.SuiteOwned,
                ),
            ]),
            "scheme_b": _make_scheme_props("scheme_b", [
                _make_arg("x", standard_name="std_b", model_var_name="x"),
            ]),
        }

    def test_suite_owned_entry_does_not_cause_a_false_collision(self):
        by_bare = _chost_scan_scheme_phase_args(
            ["scheme_a", "scheme_b"], self._meta_data(), ("_run",),
        )
        local_to_std, _ = _chost_resolve_scheme_arg_identities(by_bare)
        # Only scheme_b's real input participates -- resolves via the
        # plain bare name, exactly as suite_cap.py itself would (no
        # collision, since the SuiteOwned entry was never a candidate).
        assert local_to_std == {"x": "std_b"}


class TestScalarIntentOutArgExcludedFromCollisionDetection:
    """Same shape, but the excluded sibling is a scalar intent(out) value
    (goes to suite_cap.py's own output_arg_list, never input_arg_list)
    instead of a SuiteOwned one."""

    def _meta_data(self):
        return {
            "scheme_a": _make_scheme_props("scheme_a", [
                _make_arg("x", standard_name="scalar_out_std", model_var_name="host_a",
                          intent="out"),
            ]),
            "scheme_b": _make_scheme_props("scheme_b", [
                _make_arg("x", standard_name="std_b", model_var_name="x"),
            ]),
        }

    def test_scalar_out_entry_does_not_cause_a_false_collision(self):
        by_bare = _chost_scan_scheme_phase_args(
            ["scheme_a", "scheme_b"], self._meta_data(), ("_run",),
        )
        local_to_std, _ = _chost_resolve_scheme_arg_identities(by_bare)
        assert local_to_std == {"x": "std_b"}

    def test_array_intent_out_is_not_excluded(self):
        """An intent(out) arg WITH dims is a real input (suite_cap.py's own
        _has_dims check) -- must NOT be filtered out just for being
        intent(out)."""
        meta_data = {
            "scheme_a": _make_scheme_props("scheme_a", [
                _make_arg("y", standard_name="array_out_std", model_var_name="y",
                          intent="out", dimensions=1),
            ]),
        }
        by_bare = _chost_scan_scheme_phase_args(["scheme_a"], meta_data, ("_run",))
        local_to_std, _ = _chost_resolve_scheme_arg_identities(by_bare)
        assert local_to_std == {"y": "array_out_std"}


class TestPfnHintsCrossCheckCatchesUnfilteredExclusions:
    """The ncol -> col_start/col_end replacement (or any other
    suite_cap.py exclusion this module's own explicit filters don't know
    about) is caught by the pfn_hints cross-check safety net instead:
    scheme_a's "ncol" (standard horizontal_loop_extent) never reaches the
    real compiled signature at all once replaced, so it must not
    participate in a collision with scheme_b's unrelated real "ncol"
    input even though the raw scan sees 2 entries."""

    def _meta_data(self):
        return {
            "scheme_a": _make_scheme_props("scheme_a", [
                _make_arg("ncol", standard_name="horizontal_loop_extent",
                          model_var_name="ncol"),
            ]),
            "scheme_b": _make_scheme_props("scheme_b", [
                _make_arg("ncol", standard_name="std_b", model_var_name="ncol"),
            ]),
        }

    def test_without_pfn_hints_both_would_collide(self):
        """Confirms the raw scan really does see 2 entries here -- the
        cross-check in the next test is doing real work, not a no-op."""
        by_bare = _chost_scan_scheme_phase_args(
            ["scheme_a", "scheme_b"], self._meta_data(), ("_run",),
        )
        local_to_std, _ = _chost_resolve_scheme_arg_identities(by_bare)
        # Both share model_var_name "ncol" -- the second to resolve wins
        # (a real build can't actually produce this; it's here only to
        # show the raw, unfiltered result before the cross-check applies).
        assert local_to_std == {"ncol": "std_b"}

    def test_with_pfn_hints_the_replaced_entry_is_dropped(self):
        """pfn_hints reflects what the real signature actually contains
        after the ncol replacement -- no "ncol" at all (col_start/col_end
        instead) -- so scheme_a's entry is dropped entirely, leaving
        scheme_b's real "ncol" input correctly resolved alone."""
        by_bare = _chost_scan_scheme_phase_args(
            ["scheme_a", "scheme_b"], self._meta_data(), ("_run",),
        )
        local_to_std, _ = _chost_resolve_scheme_arg_identities(
            by_bare, pfn_hints=["col_start", "col_end", "ncol", "errmsg", "errflg"],
        )
        assert local_to_std == {"ncol": "std_b"}


# ---------------------------------------------------------------------------
# Copilot PR #113 review, finding 2: _LC_TO_ENTRY_SUFFIX alone only records
# one accepted spelling for several lifecycles -- _chost_scheme_phase_suffixes
# must return every spelling cap_shared.py's own authoritative
# _PHASE_SUFFIXES (split_scheme_table_name) accepts too.
# ---------------------------------------------------------------------------


class TestChostSchemePhaseSuffixesIncludesEveryAcceptedSpelling:
    def test_timestep_initial_includes_both_spellings(self):
        suffixes = _chost_scheme_phase_suffixes("timestep_initial")
        assert "_timestep_initialize" in suffixes
        assert "_timestep_init" in suffixes

    def test_timestep_final_includes_both_spellings(self):
        suffixes = _chost_scheme_phase_suffixes("timestep_final")
        assert "_timestep_finalize" in suffixes
        assert "_timestep_final" in suffixes

    def test_finalize_includes_both_spellings(self):
        suffixes = _chost_scheme_phase_suffixes("finalize")
        assert "_finalize" in suffixes
        assert "_final" in suffixes

    def test_physics_final_reuses_finalize_spellings(self):
        """physics_final has no originating scheme-table phase of its own
        -- it reuses "finalize"'s own scheme-table suffixes."""
        suffixes = _chost_scheme_phase_suffixes("physics_final")
        assert "_finalize" in suffixes
        assert "_final" in suffixes

    def test_a_real_short_form_scheme_table_is_now_found(self):
        """kessler_update-shaped real example: a scheme using the short
        "_timestep_init" form (atmospheric_physics/kessler_update
        convention) for a "timestep_initial" lifecycle. Before the fix,
        _chost_scheme_phase_suffixes's predecessor (a plain
        _LC_TO_ENTRY_SUFFIX.get(lc, ...) lookup) only tried
        "_timestep_initial" -- a spelling no real scheme table uses at
        all -- so this scheme's own args were never found, silently
        losing their standard-name/dimension classification."""
        meta_data = {
            "kessler_update": _make_scheme_props(
                "kessler_update",
                [_make_arg("temp", standard_name="air_temperature", model_var_name="temp")],
                phase_suffix="_timestep_init",
            ),
        }
        suffixes = _chost_scheme_phase_suffixes("timestep_initial")
        by_bare = _chost_scan_scheme_phase_args(["kessler_update"], meta_data, suffixes)
        local_to_std, _ = _chost_resolve_scheme_arg_identities(by_bare)
        assert local_to_std == {"temp": "air_temperature"}
