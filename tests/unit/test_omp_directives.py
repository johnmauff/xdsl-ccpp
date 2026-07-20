"""Unit tests for OpenMP target-directive output (directive="omp").

Before this fix, print_ftn.py's CCPPOmpTargetDataBeginOp case arm called
_emit_omp_directive with clause names like "map(tofrom:" and "map(alloc:",
but the shared _emit_acc_directive helper *also* appended its own "(" before
the first variable -- the mechanism that turns ACC's bare clause names like
"copyin" into "copyin(var)". Combining the two produced a doubled, unbalanced
paren: "map(tofrom:(var1, var2)" (missing a matching close). This affected
both GPUDataPass's and GPUCcppCapPass's structured !$omp target data regions,
on both the "hosted" (map(alloc:), present-equivalent) and "hosted2"/"scratch"
(map(tofrom:), copyin/copy/copyout-equivalent) paths.

There was zero test coverage catching this: no existing test asserted on the
literal text of any OMP directive. These tests are the first real OMP
directive-output coverage in the repo, reusing test_gpu_directives.py's
existing scheme/host/suite fixtures (already designed to cover present,
copyin/copy/copyout, and host-less-scratch cases) with directive="omp"
instead of "acc", plus a small dedicated fixture for the update-clause
(scheme=host + model=device) !$omp target update from/to path, which those
shared fixtures don't cover.
"""

from io import StringIO

from xdsl.dialects.builtin import f64

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from tests.unit.test_gpu_directives import _HOST_META, _SCHEME_META, _SUITE_XML
from xdsl_ccpp.backend.print_ftn import ftnPrintContext, print_to_ftn
from xdsl_ccpp.dialects.ccpp_utils import (
    HostVarRefOp,
    OmpTargetEnterDataOp,
    OmpTargetExitDataOp,
)
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.gpu_ccpp_cap_pass import GPUCcppCapPass
from xdsl_ccpp.transforms.gpu_data_pass import GPUDataPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP


def _omp_fortran_output(run_host_match, ccpp_context) -> str:
    """Same pipeline as test_gpu_directives.py's _fortran_output, but with
    directive="omp" for both GPU passes."""
    module = run_host_match(
        scheme_metas=[_SCHEME_META],
        host_metas=[_HOST_META],
        suite_xml=_SUITE_XML,
    )
    SuiteCAP().apply(ccpp_context, module)
    GPUDataPass(directive="omp").apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    GPUCcppCapPass(directive="omp").apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fn_body(fortran: str, fn_name: str) -> str:
    body = fortran.split(f"subroutine {fn_name}")[1]
    return body.split(f"end subroutine {fn_name}")[0]


def _assert_balanced_map_clause(body: str, clause_text: str) -> None:
    """clause_text is the expected literal text, e.g. "map(alloc:hosted)" --
    asserts it appears verbatim (proving parens are balanced: exactly one
    "(" opening the whole map(...) clause, one ")" closing it, no stray
    paren after the map-type modifier's colon)."""
    assert clause_text in body, f"expected {clause_text!r} in:\n{body}"


class TestOmpTargetDataMapClauses:
    """generate-gpu-ccpp-cap / generate-gpu-data with directive="omp": the
    structured !$omp target data region's map(...) clauses must render with
    balanced parentheses."""

    def test_present_equivalent_var_renders_balanced_map_alloc(
        self, run_host_match, ccpp_context
    ):
        """'hosted' is device+device (present-equivalent) -> map(alloc:...)."""
        fortran = _omp_fortran_output(run_host_match, ccpp_context)
        run_fn = _fn_body(fortran, "TestGpu_ccpp_physics_run")
        assert "!$omp target data" in run_fn
        _assert_balanced_map_clause(run_fn, "map(alloc:hosted)")
        assert "map(alloc:(hosted" not in run_fn

    def test_copyin_equivalent_var_renders_balanced_map_tofrom(
        self, run_host_match, ccpp_context
    ):
        """'hosted2' is device scheme + host-resident model var (copyin-
        equivalent) -> map(tofrom:...) (OMP's structured region only
        distinguishes tofrom/alloc, not copyin/copyout separately)."""
        fortran = _omp_fortran_output(run_host_match, ccpp_context)
        final_fn = _fn_body(fortran, "TestGpu_ccpp_physics_timestep_final")
        assert "!$omp target data" in final_fn
        _assert_balanced_map_clause(final_fn, "map(tofrom:hosted2)")
        assert "map(tofrom:(hosted2" not in final_fn

    def test_hostless_scratch_var_renders_balanced_map_tofrom_at_suite_cap_level(
        self, run_host_match, ccpp_context
    ):
        """'scratch' has no host match -- handled by GPUDataPass at the
        suite_cap level, a separate case arm invocation of the same
        (now-fixed) clause-emission helper."""
        fortran = _omp_fortran_output(run_host_match, ccpp_context)
        suite_fn = _fn_body(fortran, "test_gpu_suite_suite_timestep_initial")
        assert "!$omp target data" in suite_fn
        _assert_balanced_map_clause(suite_fn, "map(tofrom:scratch)")
        assert "map(tofrom:(scratch" not in suite_fn

    def test_end_target_data_present_and_paired(self, run_host_match, ccpp_context):
        fortran = _omp_fortran_output(run_host_match, ccpp_context)
        run_fn = _fn_body(fortran, "TestGpu_ccpp_physics_run")
        assert "!$omp end target data" in run_fn


# ── update-clause (scheme=host + model=device) !$omp target update path ──────
#
# Not covered by the shared test_gpu_directives.py fixtures above (which have
# no update-clause variable) -- "from"/"to" clause names were never affected
# by the map(...) paren bug (they have no map(...) wrapper at all), but this
# confirms the tuple-unpacking change in _emit_acc_directive (2-tuple vs
# 3-tuple clauses) didn't regress the plain-keyword case either.

_UPDATE_SCHEME = f"""\
[ccpp-table-properties]
  name = test_omp_update_scheme
  type = scheme
[ccpp-arg-table]
  name = test_omp_update_scheme_run
  type = scheme
[ cpu_var ]
  standard_name = test_omp_cpu_only_var
  long_name = CPU-only scheme, host keeps this on GPU
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_UPDATE_HOST = """\
[ccpp-table-properties]
  name = test_omp_update_host
  type = module
[ccpp-arg-table]
  name = test_omp_update_host
  type = module
[ cpu_var ]
  standard_name = test_omp_cpu_only_var
  long_name = host var kept on the GPU
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
"""

_UPDATE_SUITE_XML = minimal_suite_xml(
    "test_omp_update_scheme", suite_name="test_omp_upd"
)


class TestOmpTargetUpdateClause:
    def test_update_from_to_render_correctly(self, run_host_match, ccpp_context):
        module = run_host_match(
            scheme_metas=[_UPDATE_SCHEME],
            host_metas=[_UPDATE_HOST],
            suite_xml=_UPDATE_SUITE_XML,
        )
        SuiteCAP().apply(ccpp_context, module)
        GPUDataPass(directive="omp").apply(ccpp_context, module)
        CCPPCAP().apply(ccpp_context, module)
        GPUCcppCapPass(directive="omp").apply(ccpp_context, module)
        out = StringIO()
        print_to_ftn(module, out)
        fortran = out.getvalue()

        run_fn = _fn_body(fortran, "TestOmpUpd_ccpp_physics_run")
        assert "target update from(cpu_var" in run_fn
        assert "target update to(cpu_var" in run_fn


# ── OmpTargetEnterDataOp / OmpTargetExitDataOp -- op-level printer coverage ──
#
# Not wired into any pass yet (that's the next step in the OMP hoisting
# plan), so there's no pipeline that can produce these ops today -- tested
# directly at the IR/printer level instead, the same way the ops themselves
# were smoke-tested at construction time when they were added.

def _make_host_var_ref(var_name: str) -> HostVarRefOp:
    return HostVarRefOp(var_name, "some_mod", f64)


class TestOmpTargetEnterExitDataPrinter:
    def test_enter_data_renders_balanced_map_clauses(self):
        ref1 = _make_host_var_ref("var1")
        ref2 = _make_host_var_ref("var2")
        ref3 = _make_host_var_ref("var3")
        op = OmpTargetEnterDataOp(to=[ref1.res, ref2.res], alloc=[ref3.res])

        out = StringIO()
        ctx = ftnPrintContext(output=out)
        ctx.register_binops()
        ctx.variables[ref1.res] = "var1"
        ctx.variables[ref2.res] = "var2"
        ctx.variables[ref3.res] = "var3"
        ctx.print_op(op)

        text = out.getvalue()
        assert "!$omp target enter data map(to:var1, var2) map(alloc:var3)" in text
        assert "map(to:(var1" not in text
        assert "map(alloc:(var3" not in text

    def test_exit_data_renders_balanced_map_clauses(self):
        ref1 = _make_host_var_ref("var1")
        ref2 = _make_host_var_ref("var2")
        ref3 = _make_host_var_ref("var3")
        op = OmpTargetExitDataOp(from_=[ref1.res], release=[ref2.res, ref3.res])

        out = StringIO()
        ctx = ftnPrintContext(output=out)
        ctx.register_binops()
        ctx.variables[ref1.res] = "var1"
        ctx.variables[ref2.res] = "var2"
        ctx.variables[ref3.res] = "var3"
        ctx.print_op(op)

        text = out.getvalue()
        assert "!$omp target exit data map(from:var1) map(release:var2, var3)" in text
        assert "map(from:(var1" not in text
        assert "map(release:(var2" not in text
