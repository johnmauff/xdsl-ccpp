"""Unit tests for print_ftn.render_scheme_io_capture_test_driver -- the
Fortran-syntax side of the scheme-io-capture generated test driver (see
scheme_io_capture_pass.py's own module docstring for the language-
boundary rationale). No prior test file exercised this function's output
text directly; everything up to now was covered only indirectly through
the real examples/kessler end-to-end verification. Covers
scheme-io-capture-multi-timestep (every captured call for a phase is
replayed in a loop, not just the first) and
scheme-io-capture-compare-diagnostics (a FAIL reports more than a bare
pass/fail: max/mean abs diff and a mismatch location for array compares,
the actual/expected values directly for scalar compares).
"""

from xdsl_ccpp.backend.print_ftn import (
    TestDriverParam,
    format_fortran_real_literal,
    render_scheme_io_capture_test_driver,
)

_TOLERANCE = "1.0e-10_kind_phys"


def test_single_phase_replays_in_a_loop_not_just_call_one():
    params = [
        TestDriverParam("ncol", "in", "integer", None, 0),
        TestDriverParam("theta", "inout", "real", "kind_phys", 2, dims=["ncol", "nz"]),
        TestDriverParam("nz", "in", "integer", None, 0),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    source = render_scheme_io_capture_test_driver(
        "kessler", [("kessler_run", params)], _TOLERANCE,
    )

    # A real loop, not a one-shot call_count=1 read.
    assert "call_count = 1" in source
    assert "  do\n" in source
    assert "if (.not. found) exit" in source
    assert "call_count = call_count + 1" in source
    assert "  end do" in source
    # Every read in the loop drives off the shared loop variable, not a
    # hardcoded literal.
    assert 'call_count=1)' not in source
    assert "call_count=call_count, found=found" in source
    # report() now carries the call_count so a human can tell which
    # replayed call failed.
    assert "ok = ccpp_capture_compare(theta, theta_expected, " in source
    assert 'call report("theta", call_count, ok, n_failed)' in source
    assert "subroutine report(name, call_count, ok, n_failed)" in source
    # compare-diagnostics: a FAIL on a ranked (array) compare prints
    # max/mean abs diff and the first mismatching element's location, not
    # just a bare pass/fail.
    assert "if (.not. ok) write(*,*) '  max abs diff=', diag_max_abs_diff" in source
    assert "first mismatch at linear index=', diag_first_mismatch_index" in source


def test_array_allocation_is_reallocated_each_iteration():
    # A real scheme's own column count can differ call to call (different
    # chunks) -- allocation must be guarded and repeated inside the loop,
    # not done once up front.
    params = [
        TestDriverParam("ncol", "in", "integer", None, 0),
        TestDriverParam("nz", "in", "integer", None, 0),
        TestDriverParam("theta", "inout", "real", "kind_phys", 2, dims=["ncol", "nz"]),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    source = render_scheme_io_capture_test_driver(
        "kessler", [("kessler_run", params)], _TOLERANCE,
    )
    assert "if (allocated(theta)) deallocate(theta)" in source
    assert "allocate(theta(ncol, nz))" in source
    # The allocate must be inside the loop body (after "do", before "end
    # do"), not hoisted above it.
    do_idx = source.index("\n  do\n")
    end_do_idx = source.index("  end do")
    alloc_idx = source.index("if (allocated(theta)) deallocate(theta)")
    assert do_idx < alloc_idx < end_do_idx


def test_errflg_check_reports_call_count():
    params = [
        TestDriverParam("lv_in", "in", "real", "kind_phys", 0),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    source = render_scheme_io_capture_test_driver(
        "kessler", [("kessler_init", params)], _TOLERANCE,
    )
    assert "write(*,*) 'FAIL: kessler_init returned errflg=', errflg, ' (call ', call_count, ')', ' errmsg=', trim(errmsg)" in source


def test_multi_phase_still_shares_one_call_count_declaration():
    # call_count/found are declared once at the driver level (not
    # per-phase) and reused -- each phase's own loop resets call_count=1
    # independently, so a shared declaration is correct, not a collision.
    init_params = [
        TestDriverParam("lv_in", "in", "real", "kind_phys", 0),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    run_params = [
        TestDriverParam("ncol", "in", "integer", None, 0),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    source = render_scheme_io_capture_test_driver(
        "kessler", [("kessler_init", init_params), ("kessler_run", run_params)], _TOLERANCE,
    )
    assert source.count("integer :: call_count") == 1
    assert source.count("logical :: found") == 1
    assert source.count("call_count = 1") == 2


def test_scalar_compare_prints_actual_and_expected_on_fail_not_an_index():
    # A scalar has no "which index mismatched" -- the driver already has
    # both values in scope, so it should print them directly rather than
    # asking ccpp_capture_mod.F90 for a diagnostic that makes no sense
    # for a scalar.
    params = [
        TestDriverParam("out_var", "out", "integer", None, 0),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    source = render_scheme_io_capture_test_driver(
        "kessler", [("kessler_run", params)], _TOLERANCE,
    )
    # The scalar's own compare call never passes the array-style
    # diagnostic arguments -- those scratch variables are declared once
    # at the driver level regardless (harmless if unused by a particular
    # driver), but a scalar compare call site must never reference them.
    assert "ok = ccpp_capture_compare(out_var, out_var_expected)" in source
    assert 'call report("out_var", call_count, ok, n_failed)' in source
    assert (
        "if (.not. ok) write(*,*) '  actual=', out_var, ' expected=', out_var_expected"
        in source
    )
    assert "ccpp_capture_compare(out_var, out_var_expected, diag_first_mismatch_index)" not in source


def test_array_compare_diagnostics_declared_once_at_driver_level():
    params = [
        TestDriverParam("ncol", "in", "integer", None, 0),
        TestDriverParam("precl", "out", "real", "kind_phys", 1, dims=["ncol"]),
        TestDriverParam("flags", "out", "logical", None, 1, dims=["ncol"]),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    source = render_scheme_io_capture_test_driver(
        "kessler", [("kessler_run", params)], _TOLERANCE,
    )
    # Declared once, shared across every compare in the driver (real AND
    # non-real types both use first_mismatch_index; only real types also
    # use the abs-diff pair).
    assert source.count("real(kind=kind_phys) :: diag_max_abs_diff, diag_mean_abs_diff") == 1
    assert source.count("integer :: diag_first_mismatch_index") == 1
    # The logical (non-real) array compare only asks for the index, never
    # the real-only magnitude diagnostics.
    assert "ok = ccpp_capture_compare(flags, flags_expected, diag_first_mismatch_index)" in source
    assert "ccpp_capture_compare(flags, flags_expected, " + _TOLERANCE not in source


def test_format_fortran_real_literal_always_has_a_decimal_point():
    # scheme-io-capture-tolerance-config: --capture-tolerance accepts any
    # real number, including scientific notation with no literal "." in
    # it (e.g. "1e-08") -- confirmed this exact shape breaks the
    # pass-pipeline's own bare-NUMBER-token parser (see ccpp_dsl.py's own
    # comment), which is why the pass re-parses with float() and this
    # function re-renders a clean literal rather than reusing the
    # original string. A decimal point is always present even though a
    # bare mantissa+exponent is technically unambiguous Fortran, for
    # maximum portability.
    assert format_fortran_real_literal(1e-10) == "1.0e-10_kind_phys"
    assert format_fortran_real_literal(0.001) == "0.001_kind_phys"
    assert format_fortran_real_literal(5.0) == "5.0_kind_phys"
    assert format_fortran_real_literal(-1e-10) == "-1.0e-10_kind_phys"
    assert format_fortran_real_literal(1e-8, kind="r8") == "1.0e-08_r8"


def test_tolerance_parameter_is_used_verbatim_in_generated_driver():
    # render_scheme_io_capture_test_driver treats `tolerance` as an opaque
    # pre-formatted string (format_fortran_real_literal's own job, done by
    # the caller) -- confirms it's passed verbatim as the compiled-in
    # default to ccpp_capture_tolerance_override, not reformatted or
    # second-guessed here. `tolerance` is a plain variable (not a Fortran
    # `parameter`) precisely so that call can override it at run time
    # (scheme-io-capture-tolerance-config's runtime-override follow-on).
    params = [
        TestDriverParam("ncol", "in", "integer", None, 0),
        TestDriverParam("precl", "out", "real", "kind_phys", 1, dims=["ncol"]),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    source = render_scheme_io_capture_test_driver(
        "kessler", [("kessler_run", params)], "5.0e-06_kind_phys",
    )
    assert "real(kind=kind_phys) :: tolerance" in source
    assert "parameter :: tolerance" not in source
    assert "tolerance = ccpp_capture_tolerance_override(5.0e-06_kind_phys)" in source
    assert "ccpp_capture_compare(precl, precl_expected, tolerance, " in source
