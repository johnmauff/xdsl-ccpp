"""Unit tests for two real bugs in run_dispatch.py's
_build_per_suite_run_info -- the host-facing ccpp_cap wrapper's own
resolution of the *outer* dummy arguments it dispatches into each suite
callee, a separate layer from suite_cap.py's dummy-argument collision
handling (see test_suite_arg_name_collision.py, which covers the *inner*
suite subroutine's own signature).

Found while porting examples/var_compat and diagnosing why
scalar_varA/scalar_varB/scalar_varC/num_subcycles still showed up as
caller-block arguments on ccpp_physics_run even after
suite_cap.py correctly disambiguated and threaded them through the suite
subroutine's own signature.

Bug 1 -- bare-name collision. local_to_host_info was keyed by each scheme's
own literal (un-renamed) local arg name. When two or more schemes reuse the
same bare name for genuinely different standard_names (var_compat's
effr_pre/effr_post/effr_diag all declaring their own "scalar_var"), only the
first-processed scheme's entry was ever inserted (the existing
"if bare_name not in local_to_host_info" guard) -- the other two silently
fell back to ArgSourceKind.Block, even though suite_cap.py's own
_build_block_signature (_hint_for) had already renamed each of their suite
subroutine dummy args to a distinct, resolvable host name.

Fixed by grouping host-matched fn_args by bare local name, deduplicated by
standard_name (mirroring suite_cap.py's own all_args construction, which
dedupes by std_key -- without this dedup step, several schemes correctly
sharing one bare name for the *same* standard_name, e.g. every scheme's own
"ncol", would be miscounted as a collision too). A bare name backed by only
one distinct standard_name keeps the simple bare-name key (matching the
common, non-colliding case exactly as before); a bare name genuinely shared
by 2+ distinct standard_names is instead keyed by each sibling's own
host-matched canonical name (model_var_name) -- precisely what suite_cap.py
renamed that sibling's own dummy argument to.

Bug 2 -- num_subcycles DDT-scan gap. A dynamic subcycle loop count
synthesized directly by suite_cap.py's _synthesize_dynamic_loop_count_args
(var_compat's num_subcycles) is never declared in any scheme's own arg
table at all. The fallback that resolves such an arg's standard_name (for
suite-level args like col_start/col_end that don't come from a scheme arg)
only ever scanned HOST/MODULE tables, never DDT -- so it could never
discover that num_subcycles is really a member of the physics_state DDT,
and the arg fell all the way through to ArgSourceKind.Block.

Fixed by extending that scan to DDT tables too, and recording any DDT-table
match into local_to_host_info as a DdtMember entry (mirroring the same
(member_name, ddt_type_name, is_ddt=True) shape the scheme-arg path already
produces), so it resolves through the existing _resolve_ddt_access_path
machinery instead of falling back to a block argument.
"""

from xdsl_ccpp.dialects.ccpp import ArgSourceKind
from xdsl_ccpp.transforms.run_dispatch import (
    _build_per_suite_run_info,
    _RunMetadataMaps,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    CCPPArgument,
    CCPPArgumentTable,
    CCPPTableProperties,
)

# ---------------------------------------------------------------------------
# Helpers (same convention as test_run_dispatch.py)
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


def _make_scheme_props(scheme_name, args):
    props = CCPPTableProperties()
    props.setAttr("name", scheme_name)
    props.setAttr("type", "scheme")
    props.arg_tables[scheme_name + "_run"] = _make_arg_table(
        scheme_name + "_run", args, "scheme"
    )
    return props


def _assert_resolved_arg_op(
    op, arg_name, kind, *, var_name=None, module_name=None, member_path=None, std_name=None
):
    op.verify()
    assert op.arg_name.data == arg_name
    assert op.source_kind.data == kind
    assert (op.var_name.data if op.var_name is not None else None) == var_name
    assert (op.module_name.data if op.module_name is not None else None) == module_name
    assert (op.member_path.data if op.member_path is not None else None) == member_path
    assert (op.std_name.data if op.std_name is not None else None) == std_name


def _run(callee_input_names, meta_data, maps, scheme_names, cap_var_map=None):
    public_fns = {
        "test_suite_callee": (
            "test_suite_cap_mod",
            [],
            [None] * len(callee_input_names),
            callee_input_names,
        ),
    }
    suite_run_entries = [("test_suite", "run", "test_suite_callee", scheme_names)]
    per_suite, _host_global_ops = _build_per_suite_run_info(
        suite_run_entries,
        public_fns,
        meta_data,
        maps,
        cap_var_map or {},
        seen_host_globals=set(),
    )
    assert len(per_suite) == 1
    return per_suite[0]["resolved_arg_ops"]


def _bare_maps():
    return _RunMetadataMaps(
        host_var_map={},
        host_block_std_names=set(),
        constituent_std_names=set(),
        ddt_type_names=set(),
        ddt_instance_map={},
        ddt_parent_map={},
    )


# ---------------------------------------------------------------------------
# Bug 1: bare-name collision across three or more schemes
# ---------------------------------------------------------------------------

class TestBareNameCollisionAcrossSchemes:
    """Three schemes each declare their own arg literally named "x" for three
    distinct standard_names, mirroring var_compat's effr_pre/effr_post/
    effr_diag all using "scalar_var". One of the three (scheme_b) happens to
    have a model_var_name identical to its own bare name -- the tricky case
    that keeps its dummy argument unrenamed at the suite_cap layer, and which
    an earlier, blunter fix attempt got wrong (see git history / PR
    discussion): unconditionally overwriting the bare-name key by
    model_var_name clobbered scheme_b's own correct entry whenever a
    different, unrelated scheme's model_var_name happened to equal a
    completely different arg's bare name."""

    def _meta_data(self):
        return {
            "scheme_a": _make_scheme_props("scheme_a", [
                _make_arg(
                    "x", standard_name="std_a",
                    model_var_name="host_a", model_module_name="test_host_mod",
                ),
            ]),
            "scheme_b": _make_scheme_props("scheme_b", [
                _make_arg(
                    "x", standard_name="std_b",
                    model_var_name="x", model_module_name="test_host_mod",
                ),
            ]),
            "scheme_c": _make_scheme_props("scheme_c", [
                _make_arg(
                    "x", standard_name="std_c",
                    model_var_name="host_c", model_module_name="test_host_mod",
                ),
            ]),
        }

    def test_each_sibling_resolves_to_its_own_host_var(self):
        # Mirrors what suite_cap.py's _build_block_signature actually prints
        # for these three colliding args: scheme_a and scheme_c get renamed
        # to their own model_var_name; scheme_b keeps "x" unchanged since its
        # model_var_name already equals its bare name.
        callee_input_names = ["host_a", "x", "host_c"]
        ops = _run(callee_input_names, self._meta_data(), _bare_maps(), scheme_names=[
            "scheme_a", "scheme_b", "scheme_c",
        ])
        assert len(ops) == 3
        _assert_resolved_arg_op(
            ops[0], "host_a", ArgSourceKind.Host,
            var_name="host_a", module_name="test_host_mod",
        )
        _assert_resolved_arg_op(
            ops[1], "x", ArgSourceKind.Host,
            var_name="x", module_name="test_host_mod",
        )
        _assert_resolved_arg_op(
            ops[2], "host_c", ArgSourceKind.Host,
            var_name="host_c", module_name="test_host_mod",
        )

    def test_order_independent(self):
        """The fix must not depend on which colliding scheme happens to be
        processed first -- reversing scheme_names must give the same result."""
        callee_input_names = ["host_a", "x", "host_c"]
        ops = _run(callee_input_names, self._meta_data(), _bare_maps(), scheme_names=[
            "scheme_c", "scheme_b", "scheme_a",
        ])
        assert len(ops) == 3
        _assert_resolved_arg_op(
            ops[0], "host_a", ArgSourceKind.Host,
            var_name="host_a", module_name="test_host_mod",
        )
        _assert_resolved_arg_op(
            ops[1], "x", ArgSourceKind.Host,
            var_name="x", module_name="test_host_mod",
        )
        _assert_resolved_arg_op(
            ops[2], "host_c", ArgSourceKind.Host,
            var_name="host_c", module_name="test_host_mod",
        )


class TestRepeatedIdenticalMatchIsNotACollision:
    """Two schemes independently declare their own arg literally named
    "ncol", both mapped to the *same* standard_name and the *same*
    model_var_name (var_compat's real "ncol" -> "ncols" case). This must
    resolve via the plain bare-name key, exactly as before -- an earlier,
    naive fix attempt (counting raw fn_arg occurrences instead of
    deduplicating by standard_name) miscounted this as a collision and
    incorrectly rerouted it through model_var_name, breaking a
    previously-correct resolution."""

    def _meta_data(self):
        return {
            "scheme_a": _make_scheme_props("scheme_a", [
                _make_arg(
                    "ncol", standard_name="horizontal_dimension",
                    model_var_name="ncols", model_module_name="test_host_mod",
                ),
            ]),
            "scheme_b": _make_scheme_props("scheme_b", [
                _make_arg(
                    "ncol", standard_name="horizontal_dimension",
                    model_var_name="ncols", model_module_name="test_host_mod",
                ),
            ]),
        }

    def test_resolves_via_bare_name(self):
        ops = _run(["ncol"], self._meta_data(), _bare_maps(), scheme_names=[
            "scheme_a", "scheme_b",
        ])
        assert len(ops) == 1
        _assert_resolved_arg_op(
            ops[0], "ncol", ArgSourceKind.Host,
            var_name="ncols", module_name="test_host_mod",
        )


# ---------------------------------------------------------------------------
# Bug 2: a suite-level synthesized arg with no scheme table entry, whose
# host-side name only exists as a DDT member
# ---------------------------------------------------------------------------

class TestSynthesizedArgResolvesThroughDDTTable:
    """num_subcycles-shaped case: the callee arg appears in no scheme's own
    arg table at all (it's synthesized directly by suite_cap.py), and its
    host-side local name is a member of a DDT instantiated at module level,
    not a plain HOST/MODULE-table variable."""

    def _meta_data(self):
        ddt_props = CCPPTableProperties()
        ddt_props.setAttr("name", "phys_state_t")
        ddt_props.setAttr("type", "ddt")
        ddt_props.arg_tables["phys_state_t"] = _make_arg_table(
            "phys_state_t",
            [_make_arg("num_subcycles", standard_name="num_subcycles_for_effr")],
            "ddt",
        )

        mod_props = CCPPTableProperties()
        mod_props.setAttr("name", "test_host_mod")
        mod_props.setAttr("type", "module")
        mod_props.arg_tables["test_host_mod"] = _make_arg_table(
            "test_host_mod", [], "module"
        )

        return {"phys_state_t": ddt_props, "test_host_mod": mod_props}

    def _maps(self):
        return _RunMetadataMaps(
            host_var_map={},
            host_block_std_names=set(),
            constituent_std_names=set(),
            ddt_type_names={"phys_state_t"},
            ddt_instance_map={"phys_state_t": ("phys_state", "test_host_mod")},
            ddt_parent_map={},
        )

    def test_resolves_as_ddt_member_not_block(self):
        # No scheme declares this arg at all -- scheme_names is empty.
        ops = _run(["num_subcycles"], self._meta_data(), self._maps(), scheme_names=[])
        assert len(ops) == 1
        _assert_resolved_arg_op(
            ops[0], "num_subcycles", ArgSourceKind.DdtMember,
            var_name="phys_state", module_name="test_host_mod",
            member_path="num_subcycles",
        )
