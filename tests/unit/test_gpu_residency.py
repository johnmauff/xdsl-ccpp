"""Unit tests for HostMatched present/update GPU residency establishment.

present()/update self/update device are all pure assertions/syncs -- none of
them *allocate* anything (see GPUCcppCapPass's class docstring: "the host
model is responsible for managing the device copy independently of this
framework"). Before this fix, a host var declared memory_space=device got
zero residency establishment from xdsl_ccpp regardless of clause -- if
nothing else (a larger host model's own infrastructure, or hand-written
!$acc directives) put it on the device, present()/update self/device would
fail at runtime with "data in PRESENT clause was not found on device" --
exactly the error reported for examples/advection_flat_host's qv.

_analyze_one_suite_residency/_wrap_residency_directives establish this
automatically, driven by the same memory_space=device metadata, independent
of whether the var resolves to present, update, or diverges between the two
across schemes (see cap_shared.find_diverged_suite_vars) -- residency is a
simple "does anything need this on the device" union, not a per-scheme
clause choice.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.gpu_ccpp_cap_pass import GPUCcppCapPass
from xdsl_ccpp.transforms.gpu_data_pass import GPUDataPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

import pytest

pytestmark = pytest.mark.usefixtures("legacy_mode")


def _fortran_output(run_host_match, ccpp_context, scheme_metas, host_metas, suite_xml) -> str:
    module = run_host_match(
        scheme_metas=scheme_metas,
        host_metas=host_metas,
        suite_xml=suite_xml,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    GPUDataPass(directive="acc").apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    GPUCcppCapPass(directive="acc").apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fn_body(fortran: str, fn_name: str) -> str:
    return fortran.split(f"subroutine {fn_name}")[1].split(f"end subroutine {fn_name}")[0]


def _var_in_clause(body: str, clause: str, var_name: str) -> bool:
    """True if var_name appears inside a `clause(...)` argument list anywhere
    in body -- multiple residency vars at the same call site are legitimately
    combined into one directive (e.g. `copy(present_var, update_var)`), so a
    plain f"{clause}({var_name}" substring check only works when var_name
    happens to be listed first."""
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith(f"!$acc data {clause}(") and f"{clause}(" not in stripped:
            continue
        start = stripped.find(f"{clause}(")
        if start == -1:
            continue
        end = stripped.find(")", start)
        args = stripped[start + len(clause) + 1:end]
        if var_name in [a.strip() for a in args.split(",")]:
            return True
    return False


# ── Single-phase present/update vars (both used only at _run) ────────────────

_SINGLE_PHASE_SCHEME = f"""\
[ccpp-table-properties]
  name = test_residency_scheme
  type = scheme
[ccpp-arg-table]
  name = test_residency_scheme_run
  type = scheme
[ present_var ]
  standard_name = test_present_residency_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = inout
[ update_var ]
  standard_name = test_update_residency_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_SINGLE_PHASE_HOST = """\
[ccpp-table-properties]
  name = test_residency_host
  type = module
[ccpp-arg-table]
  name = test_residency_host
  type = module
[ present_var ]
  standard_name = test_present_residency_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
[ update_var ]
  standard_name = test_update_residency_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
"""

_SINGLE_PHASE_SUITE_XML = minimal_suite_xml(
    "test_residency_scheme", suite_name="test_residency_suite"
)


class TestSinglePhaseResidency:
    def test_present_var_resident_for_the_whole_run(
        self, run_host_match, ccpp_context
    ):
        """The host declares present_var device: it is entered once in
        ccpp_init and copied back once in ccpp_final (resident-physics-state),
        and the run phase only asserts it present -- no per-call copy region."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_SINGLE_PHASE_SCHEME], [_SINGLE_PHASE_HOST], _SINGLE_PHASE_SUITE_XML,
        )
        run_fn = _fn_body(fortran, "ccpp_physics_run")
        init_fn = fortran.split("subroutine ccpp_init(")[1].split("end subroutine ccpp_init")[0]
        final_fn = fortran.split("subroutine ccpp_final(")[1].split("end subroutine ccpp_final")[0]
        assert "present(present_var" in run_fn
        assert not _var_in_clause(run_fn, "copy", "present_var")
        assert _var_in_clause(init_fn, "copyin", "present_var")
        assert _var_in_clause(final_fn, "copyout", "present_var")

    def test_update_var_resident_for_the_whole_run_keeps_its_update_pair(
        self, run_host_match, ccpp_context
    ):
        """update_var is host-declared device but used by a host scheme: it
        is resident for the whole run (entered in ccpp_init, copied back in
        ccpp_final), and pushed right after the host scheme's call inside the
        suite (host-scheme-present-coherence); no pull (no device writer),
        no per-call copy region, nothing in the host cap's run function."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_SINGLE_PHASE_SCHEME], [_SINGLE_PHASE_HOST], _SINGLE_PHASE_SUITE_XML,
        )
        run_fn = _fn_body(fortran, "ccpp_physics_run")
        init_fn = fortran.split("subroutine ccpp_init(")[1].split("end subroutine ccpp_init")[0]
        final_fn = fortran.split("subroutine ccpp_final(")[1].split("end subroutine ccpp_final")[0]
        suite_fn = next(
            chunk.split("end subroutine")[0]
            for chunk in fortran.split("\n  subroutine ")[1:]
            if "call test_residency_scheme_run(" in chunk.split("end subroutine")[0]
        )
        assert "update device(update_var" in suite_fn
        assert "update self(update_var" not in suite_fn
        assert "update_var" not in "".join(l for l in run_fn.splitlines() if "!$acc" in l)
        assert _var_in_clause(init_fn, "copyin", "update_var")
        assert _var_in_clause(final_fn, "copyout", "update_var")


# ── Multi-phase present var (initialize + run) -- real hoisting, not per-call ─

_MULTI_PHASE_SCHEME = f"""\
[ccpp-table-properties]
  name = test_residency_multi_scheme
  type = scheme
[ccpp-arg-table]
  name = test_residency_multi_scheme_init
  type = scheme
[ multi_var ]
  standard_name = test_multi_residency_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
  intent = inout
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = test_residency_multi_scheme_run
  type = scheme
[ multi_var ]
  standard_name = test_multi_residency_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_MULTI_PHASE_HOST = """\
[ccpp-table-properties]
  name = test_residency_multi_host
  type = module
[ccpp-arg-table]
  name = test_residency_multi_host
  type = module
[ multi_var ]
  standard_name = test_multi_residency_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
"""

_MULTI_PHASE_SUITE_XML = minimal_suite_xml(
    "test_residency_multi_scheme", suite_name="test_residency_multi_suite"
)


class TestMultiPhaseResidency:
    def test_hoisted_enter_at_initialize_exit_at_finalize_nothing_at_run(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_MULTI_PHASE_SCHEME], [_MULTI_PHASE_HOST], _MULTI_PHASE_SUITE_XML,
        )
        init_fn = _fn_body(fortran, "ccpp_init")
        run_fn = _fn_body(fortran, "ccpp_physics_run")
        finalize_fn = _fn_body(fortran, "ccpp_final")

        assert "enter data copyin(multi_var" in init_fn
        assert "exit data copyout(multi_var" in finalize_fn
        # No per-call re-transfer at run -- only the unchanged present()
        # assertion, no separate copy()/enter-data/exit-data line for it.
        for line in run_fn.splitlines():
            stripped = line.strip()
            if "multi_var" in stripped and "!$acc" in stripped:
                assert stripped.startswith("!$acc data present") or "present(multi_var" in stripped


# ── Regression: copy-family var (scheme=device, model=host) unaffected ───────

_COPY_FAMILY_SCHEME = f"""\
[ccpp-table-properties]
  name = test_residency_copyfamily_scheme
  type = scheme
[ccpp-arg-table]
  name = test_residency_copyfamily_scheme_run
  type = scheme
[ copy_var ]
  standard_name = test_copyfamily_residency_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_COPY_FAMILY_HOST = """\
[ccpp-table-properties]
  name = test_residency_copyfamily_host
  type = module
[ccpp-arg-table]
  name = test_residency_copyfamily_host
  type = module
[ copy_var ]
  standard_name = test_copyfamily_residency_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
"""

_COPY_FAMILY_SUITE_XML = minimal_suite_xml(
    "test_residency_copyfamily_scheme", suite_name="test_residency_copyfamily_suite"
)


class TestCopyFamilyResidencyRegression:
    def test_copy_family_var_gets_no_separate_residency_treatment(
        self, run_host_match, ccpp_context
    ):
        """scheme=device + model=host is copy-family, not present/update --
        _analyze_one_suite_residency's model_var_memory_space=="device" gate
        never matches it (the host itself is NOT device-resident), so it's
        untouched by this new mechanism entirely; it keeps its existing,
        unchanged copy()-region-only treatment from _wrap_scheme_call."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_COPY_FAMILY_SCHEME], [_COPY_FAMILY_HOST], _COPY_FAMILY_SUITE_XML,
        )
        run_fn = _fn_body(fortran, "ccpp_physics_run")
        assert run_fn.count("!$acc data copy(copy_var") == 1
        assert "enter data" not in run_fn
        assert "exit data" not in run_fn
