"""Unit test for task #60: lifecycle_cap.py's _generate_lifecycle_fn resolving
a framework cap-var (FRAMEWORK_STD_NAME_TO_CAP_VAR) INPUT arg on a non-_run
lifecycle phase.

Found while scoping task #60 (investigate unifying lifecycle_cap.py's arg
resolution with run_dispatch.py's ResolvedArgOp pattern): run_dispatch.py's
own "_run" dispatch (_build_per_suite_run_info) explicitly checks
`std_name in cap_var_map` to resolve a CapVar-sourced input
(ArgSourceKind.CapVar) -- but _generate_lifecycle_fn's input-arg resolution
loop never did the same check. A framework-array input on register/init/
finalize/timestep_* fell through to the same "not host-matched" fallback
used for genuinely unmatched optional/allocatable args, allocating a fresh,
uninitialized local instead of referencing the real, persisted cap-module
variable -- the same bug class as test_lifecycle_ddt_member_resolution.py's
DDT-member finding and the opt_arg HOST-table-arg bug.

The fix is deliberately narrower than "any std_name in cap_var_map": a real
regression surfaced while verifying it against examples/ddthost -- cap_var_map
ALSO accumulates plain CapScratch scratch vars keyed only by standard_name,
and two unrelated schemes' own unmatched args can share one standard_name by
pure coincidence (examples/ddthost's own "vmr" case), each meaning a fresh,
call-scoped value with no cross-call relationship at all. Only
FRAMEWORK_STD_NAME_TO_CAP_VAR's names (ccpp_constituents,
ccpp_constituent_tendencies, ...) are a real identity guarantee -- always the
one shared, always-declared framework array by design -- so the fix is
scoped to exactly those.

Confirmed latent, not live: no current example's non-_run lifecycle phase
needs a framework-array input today, and ccpp_cap.py's own _build_cap_var_map
only ever populates cap_var_map's framework entries from a real cross-scheme/
cross-group _run shape (this codebase has no example combining that with a
non-_run consumer). Rather than force a synthetic multi-group fixture just to
get _build_cap_var_map to populate itself naturally -- a separate concern
from the actual resolution bug -- this test drives _generate_lifecycle_fn's
own consumption of cap_var_map directly: scheme_a's _init declares one
intent(in) ccpp_constituent_tendencies input, and _build_cap_var_map is
monkeypatched to return a cap_var_map already containing that standard_name,
exactly mirroring the shape a real cross-scheme case would hand it. This
isolates the resolution fix itself from the separate question of how
cap_var_map gets populated.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms import ccpp_cap as ccpp_cap_mod
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

_HOST_MOD_META = """\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
"""

_SCHEME_META = f"""\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
[ccpp-arg-table]
  name = scheme_a_init
  type = scheme
[ consumed ]
  standard_name = ccpp_constituent_tendencies
  units = m
  type = real
  kind = kind_phys
  dimensions = ()
  intent = in
  optional = True
{CCPP_MANDATORY_ARGS}
"""


def _install_fake_cap_var_map(monkeypatch):
    """Make ccpp_cap.py's own _build_cap_var_map return a cap_var_map that
    already has an entry for ccpp_constituent_tendencies -- exactly the shape a
    real cross-scheme/cross-group _run producer would populate, per that
    function's own real scan (isolated here so this test only exercises
    _generate_lifecycle_fn's own consumption of cap_var_map, not the
    separate question of how a real example would populate it)."""
    real_build = ccpp_cap_mod._build_cap_var_map

    def _fake(meta_data, suite_descriptions, public_fns, instance_local_name=None):
        cap_var_map, host_var_map_lc, scratch_var_list, framework_var_residency = (
            real_build(meta_data, suite_descriptions, public_fns, instance_local_name)
        )
        cap_var_map = dict(cap_var_map)
        cap_var_map["ccpp_constituent_tendencies"] = ("lc_real_cap_var", None, None)
        return cap_var_map, host_var_map_lc, scratch_var_list, framework_var_residency

    monkeypatch.setattr(ccpp_cap_mod, "_build_cap_var_map", _fake)


def _fortran_output(run_host_match, ccpp_context, monkeypatch) -> str:
    _install_fake_cap_var_map(monkeypatch)
    module = run_host_match(
        scheme_metas=[_SCHEME_META],
        host_metas=[_HOST_MOD_META],
        suite_xml=minimal_suite_xml("scheme_a"),
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fn_body(fortran: str, fn_name: str) -> str:
    return fortran.split(f"subroutine {fn_name}")[1].split(f"end subroutine {fn_name}")[0]


class TestLifecycleInitResolvesCapScratchInput:
    """scheme_a's _init consumes ccpp_constituent_tendencies, a
    FRAMEWORK_STD_NAME_TO_CAP_VAR-known (no host match, optional) standard_name
    that cap_var_map already has an entry for (e.g. from a real cross-scheme
    _run producer, injected here directly -- see module docstring)."""

    def test_init_call_uses_real_cap_var_not_fresh_local(
        self, run_host_match, ccpp_context, monkeypatch
    ):
        fortran = _fortran_output(run_host_match, ccpp_context, monkeypatch)
        fn = _fn_body(fortran, "ccpp_init")
        call_line = next(
            line for line in fn.splitlines() if "call test_suite_suite_initialize" in line
        )
        assert "lc_real_cap_var" in call_line, (
            f"expected the real cap-owned module var threaded into the call, "
            f"got: {call_line!r}"
        )

    def test_no_fresh_uninitialized_local_declared(
        self, run_host_match, ccpp_context, monkeypatch
    ):
        """The actual bug this fix closes: a fresh 'lc_consumed' local was
        declared and passed instead of the persisted cap var, silently
        discarding whatever value the real producer had set."""
        fortran = _fortran_output(run_host_match, ccpp_context, monkeypatch)
        fn = _fn_body(fortran, "ccpp_init")
        assert "lc_consumed" not in fn, (
            f"dead/wrong scratch local still declared and used:\n{fn}"
        )
