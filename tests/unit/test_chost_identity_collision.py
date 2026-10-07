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

from xdsl_ccpp.transforms.cpp_interop import (
    _chost_resolve_scheme_arg_identities,
    _chost_scan_scheme_phase_args,
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
