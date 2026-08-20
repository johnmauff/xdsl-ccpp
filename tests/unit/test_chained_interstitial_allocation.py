"""Unit tests for task #30's chained-interstitial allocation-ordering fix.

Two independent, complementary mechanisms in suite_cap.py's
_build_framework_refs/_build_call_ops:

1. Explicit scheme-self-allocation: a SuiteOwned primitive-type array
   marked `allocatable` in its own scheme's .meta (e.g.
   examples/suite_allocate/make_workspace.F90's own `work`) is no longer
   redundantly pre-allocated by the suite's own preamble -- the scheme's
   own hand-written Fortran already allocates it itself, and
   intent(out) on an allocatable dummy auto-deallocates on entry, so the
   suite's own prior allocation was always thrown away the instant the
   scheme was called. Harmless before this fix, just wasted work.

2. Chained-dimension deferral (the actual confirmed bug, 2026-08-17): an
   ORDINARY SuiteOwned array (no `allocatable` flag at all) whose
   allocation dimension is itself produced by another scheme's own call
   within the *same* phase's call sequence used to get allocated in the
   shared preamble, before the call that sets its own sizing scalar had
   even run. Fixed by deferring that specific var's LazyAllocOp until
   immediately after its producer scheme's own call ops are emitted, in
   _build_call_ops's existing per-scheme call-sequence walk -- no
   dependency graph or topological sort needed, since the SDF's own call
   sequence is already a valid order once producer-before-consumer is
   respected. A call sequence that never actually calls the producer (or
   nests it inside a promoted-dimension loop, out of scope for this
   fix's first cut) raises a clear error instead of silently emitting
   wrong-order Fortran.
"""

from io import StringIO
from pathlib import Path

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

_HOST_META = """\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
"""


def _scheme_c_meta(postfix: str = "_register") -> str:
    return f"""\
[ccpp-table-properties]
  name = scheme_c
  type = scheme
[ccpp-arg-table]
  name = scheme_c{postfix}
  type = scheme
[ dim_inter ]
  standard_name = dimension_for_interstitial_variable
  units = count
  dimensions = ()
  type = integer
  intent = out
{CCPP_MANDATORY_ARGS}
"""


def _scheme_a_meta(postfix: str = "_register") -> str:
    return f"""\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
[ccpp-arg-table]
  name = scheme_a{postfix}
  type = scheme
[ produced ]
  standard_name = interstitial_var
  units = count
  dimensions = (dimension_for_interstitial_variable)
  type = real
  kind = kind_phys
  intent = out
{CCPP_MANDATORY_ARGS}
"""


def _fortran_output(run_host_match, ccpp_context, suite_xml) -> str:
    module = run_host_match(
        scheme_metas=[_scheme_c_meta(), _scheme_a_meta()], host_metas=[_HOST_META],
        suite_xml=suite_xml,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fn_body(fortran: str, fn_name: str) -> str:
    return fortran.split(f"subroutine {fn_name}")[1].split(f"end subroutine {fn_name}")[0]


_FLAT_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <scheme>scheme_c</scheme>
    <scheme>scheme_a</scheme>
  </group>
</suite>
"""

_SUBCYCLE_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <subcycle loop="1">
      <scheme>scheme_c</scheme>
    </subcycle>
    <scheme>scheme_a</scheme>
  </group>
</suite>
"""


class TestChainedInterstitialAllocationOrdering:
    """scheme_c's own _register produces dim_inter; scheme_a's own
    _register produces an array dimensioned by it, within the SAME
    phase's call sequence -- the exact upstream capgen-v1 shape
    (temp_adjust.meta's interstitial_var/dimension_for_interstitial_variable)."""

    def test_allocation_happens_after_producer_call(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context, _FLAT_SUITE_XML)
        fn = _fn_body(fortran, "test_suite_suite_register")
        lines = [l.strip() for l in fn.splitlines() if l.strip()]
        producer_idx = next(i for i, l in enumerate(lines) if "call scheme_c_register" in l)
        alloc_idx = next(i for i, l in enumerate(lines) if l.startswith("allocate(produced"))
        consumer_idx = next(i for i, l in enumerate(lines) if "call scheme_a_register" in l)
        assert producer_idx < alloc_idx < consumer_idx

    def test_allocation_emitted_exactly_once(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context, _FLAT_SUITE_XML)
        fn = _fn_body(fortran, "test_suite_suite_register")
        alloc_lines = [l for l in fn.splitlines() if "allocate(produced" in l]
        assert len(alloc_lines) == 1

    def test_still_works_when_producer_is_inside_a_subcycle(self, run_host_match, ccpp_context):
        """A subcycle body's own (non-promoted) scheme calls still go
        through the same per-scheme call-sequence walk as the flat case,
        so the producer-then-consumer ordering is preserved even when the
        producer is nested one subcycle level deep."""
        fortran = _fortran_output(run_host_match, ccpp_context, _SUBCYCLE_SUITE_XML)
        fn = _fn_body(fortran, "test_suite_suite_register")
        lines = [l.strip() for l in fn.splitlines() if l.strip()]
        producer_idx = next(i for i, l in enumerate(lines) if "call scheme_c_register" in l)
        alloc_idx = next(i for i, l in enumerate(lines) if l.startswith("allocate(produced"))
        consumer_idx = next(i for i, l in enumerate(lines) if "call scheme_a_register" in l)
        assert producer_idx < alloc_idx < consumer_idx


class TestSchemeSelfAllocatedPrimitiveNoLongerDoubleAllocates:
    """examples/suite_allocate/make_workspace.F90's own `work` is declared
    `allocatable, intent(out)` and self-allocated inside the scheme's own
    body -- the suite must not also pre-allocate it. Uses the real
    example's own meta files directly (not a synthetic one-scheme
    fixture): `work`'s own sizing scalar (`nw`/workspace_dimension) is
    itself produced by use_workspace's separate `_timestep_init` entry
    point, a genuinely cross-phase producer that a synthetic single-scheme
    fixture can't reproduce without also tripping host-match requirements
    this test isn't about."""

    def test_no_redundant_preamble_allocation(self, run_host_match, ccpp_context):
        suite_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="suite_allocate_suite" version="1.0">
  <group name="workspace_group">
    <scheme>make_workspace</scheme>
    <scheme>use_workspace</scheme>
  </group>
</suite>
"""
        make_workspace_meta = (
            Path("examples/suite_allocate/make_workspace.meta").read_text()
        )
        use_workspace_meta = (
            Path("examples/suite_allocate/use_workspace.meta").read_text()
        )
        test_host_meta = Path("examples/suite_allocate/test_host.meta").read_text()
        data_meta = Path("examples/suite_allocate/data.meta").read_text()

        module = run_host_match(
            scheme_metas=[make_workspace_meta, use_workspace_meta],
            host_metas=[test_host_meta, data_meta],
            suite_xml=suite_xml,
        )
        ArgOwnershipPass().apply(ccpp_context, module)
        SuiteCAP().apply(ccpp_context, module)
        out = StringIO()
        print_to_ftn(module, out)
        fortran = out.getvalue()
        assert "allocated(work)" not in fortran
        assert "call make_workspace_run" in fortran


class TestSchemeSelfAllocatedPrimitiveViaSuiteOwnedVarsSweepSkipsPreamble:
    """Copilot review, PR #83: the suite_owned_vars() sweep (the SECOND of
    _build_framework_refs's two allocation sites) didn't check `allocatable`
    at all, so a var only reachable through that sweep -- not the
    framework_vars loop -- still got a (duplicate, wrong-order) LazyAllocOp.
    Real, confirmed example already in this repo:
    examples/capgen/scheme/environ_conditions.meta's own `model_times`
    (dimensioned by `number_of_model_times`, itself produced by the SAME
    scheme's SAME `_init` call, immediately before its own `allocate()`) --
    `environ_conditions.F90`'s `environ_conditions_init` already does
    `ntimes = input_model_times; allocate(model_times(ntimes))` itself.
    Before this fix: regenerating examples/capgen produced a redundant
    `use test_host_mod, only: num_model_times` plus TWO separate wrong
    `allocate(model_times(...))` blocks -- one keyed to the host's own
    `num_model_times` (found via the sweep's fallback to
    _find_loop_upper_bound's MODULE-table path, since environ_conditions's
    own _init table isn't part of _register's arg_tables and the sweep
    runs for both _init and _register), one keyed to the scheme's own
    `ntimes` (found via the framework_vars loop's mechanism-2 deferral).
    After this fix: no allocation of `model_times` appears in the suite-cap
    module's own generated code at all."""

    def test_no_allocation_via_the_sweep(self, run_host_match, ccpp_context):
        module_path = Path("examples/capgen/scheme")
        host_path = Path("examples/capgen/host_ftn")
        env_meta = (module_path / "environ_conditions.meta").read_text()
        make_ddt_meta = (module_path / "make_ddt.meta").read_text()
        test_host_data_meta = (host_path / "test_host_data.meta").read_text()
        test_host_mod_meta = (host_path / "test_host_mod.meta").read_text()
        test_host_meta = (host_path / "test_host.meta").read_text()

        suite_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="ddt_suite" version="1.0">
  <group name="ddt_group">
    <scheme>make_ddt</scheme>
    <scheme>environ_conditions</scheme>
  </group>
</suite>
"""
        module = run_host_match(
            scheme_metas=[env_meta, make_ddt_meta],
            host_metas=[test_host_data_meta, test_host_mod_meta, test_host_meta],
            suite_xml=suite_xml,
        )
        ArgOwnershipPass().apply(ccpp_context, module)
        SuiteCAP().apply(ccpp_context, module)
        out = StringIO()
        print_to_ftn(module, out)
        fortran = out.getvalue()
        register_body = _fn_body(fortran, "ddt_suite_suite_register")
        initialize_body = _fn_body(fortran, "ddt_suite_suite_initialize")
        assert "allocate(model_times" not in register_body
        assert "allocate(model_times" not in initialize_body
        assert "num_model_times" not in register_body
