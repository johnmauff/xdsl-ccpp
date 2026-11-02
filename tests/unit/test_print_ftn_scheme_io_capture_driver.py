"""Unit tests for print_ftn.render_scheme_io_capture_test_driver -- the
Fortran-syntax side of the scheme-io-capture generated test driver (see
scheme_io_capture_pass.py's own module docstring for the language-
boundary rationale). No prior test file exercised this function's output
text directly; everything up to now was covered only indirectly through
the real examples/kessler end-to-end verification. Covers
scheme-io-capture-multi-timestep (every captured call for a phase is
replayed in a loop over its NetCDF files, not just the first) and
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
        "kessler", [("kessler_run", params, "kessler")], _TOLERANCE,
    )

    # A real loop over the call's capture files (<table>_<n>.nc), not a
    # one-shot read of call 1.
    assert "call_count = 1" in source
    assert "  do\n" in source
    assert 'call ccpp_capture_open_call("kessler_run", call_count, found)' in source
    assert "if (.not. found) exit" in source
    assert "call_count = call_count + 1" in source
    assert "  end do" in source
    # Inputs come from the file's `in` group, results from `out`; the file
    # is closed before the compares.
    assert 'call ccpp_capture_read("in", "ncol", ncol)' in source
    assert 'call ccpp_capture_read("in", "theta", theta)' in source
    assert 'call ccpp_capture_read("out", "theta", theta_expected)' in source
    assert (source.index('ccpp_capture_read("out", "theta"')
            < source.index("call ccpp_capture_close()")
            < source.index("ok = ccpp_capture_compare(theta"))
    # No captured call at all is a FAIL, not a vacuous pass.
    assert "FAIL: no captured calls of kessler_run found" in source
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
        "kessler", [("kessler_run", params, "kessler")], _TOLERANCE,
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
        "kessler", [("kessler_init", params, "kessler")], _TOLERANCE,
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
        "kessler", [("kessler_init", init_params, "kessler"), ("kessler_run", run_params, "kessler")], _TOLERANCE,
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
        "kessler", [("kessler_run", params, "kessler")], _TOLERANCE,
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
        "kessler", [("kessler_run", params, "kessler")], _TOLERANCE,
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
        "kessler", [("kessler_run", params, "kessler")], "5.0e-06_kind_phys",
    )
    assert "real(kind=kind_phys) :: tolerance" in source
    assert "parameter :: tolerance" not in source
    assert "tolerance = ccpp_capture_tolerance_override(5.0e-06_kind_phys)" in source
    assert "ccpp_capture_compare(precl, precl_expected, tolerance, " in source


# scheme-io-capture-gpu-residency: a generated driver is a standalone
# program with no surrounding suite-level device residency to lean on, so
# a memory_space=device argument needs its own device copy established
# before the call and torn down after -- unlike a real cap, which only
# needs an `update self` sync before reading a value back for capture
# (there's already a device copy to sync from, established elsewhere).


def test_inout_device_array_gets_enter_copyin_and_exit_copyout():
    params = [
        TestDriverParam("ncol", "in", "integer", None, 0),
        TestDriverParam("theta", "inout", "real", "kind_phys", 1, dims=["ncol"], is_device=True),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    source = render_scheme_io_capture_test_driver(
        "kessler", [("kessler_run", params, "kessler")], _TOLERANCE, directive="acc",
    )
    assert "!$acc enter data copyin(theta)" in source
    assert "!$acc exit data copyout(theta)" in source
    # Never both directions for the same array in the same directive.
    assert "!$acc enter data create(theta)" not in source
    assert "!$acc exit data delete(theta)" not in source
    # Ordering: enter-data after theta is allocated/read but before the
    # call; exit-data after the call but before theta is compared --
    # otherwise the driver would compare against theta's stale pre-call
    # host value instead of the scheme's real, device-computed result.
    enter_idx = source.index("!$acc enter data copyin(theta)")
    call_idx = source.index("call kessler_run(")
    exit_idx = source.index("!$acc exit data copyout(theta)")
    compare_idx = source.index("ccpp_capture_compare(theta, theta_expected")
    assert enter_idx < call_idx < exit_idx < compare_idx


def test_in_only_device_array_gets_enter_copyin_and_exit_delete():
    # Never read back (no :after capture exists for an in-only arg), so
    # the exit side only needs to release the device copy, not transfer
    # it back.
    params = [
        TestDriverParam("ncol", "in", "integer", None, 0),
        TestDriverParam("cpair", "in", "real", "kind_phys", 1, dims=["ncol"], is_device=True),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    source = render_scheme_io_capture_test_driver(
        "kessler", [("kessler_run", params, "kessler")], _TOLERANCE, directive="acc",
    )
    assert "!$acc enter data copyin(cpair)" in source
    assert "!$acc exit data delete(cpair)" in source
    assert "copyout(cpair)" not in source


def test_out_only_device_array_gets_enter_create_and_exit_copyout():
    # No captured "before" value exists for an out-only arg -- nothing
    # useful to transfer to the device yet, just allocate it there.
    params = [
        TestDriverParam("ncol", "in", "integer", None, 0),
        TestDriverParam("precl", "out", "real", "kind_phys", 1, dims=["ncol"], is_device=True),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    source = render_scheme_io_capture_test_driver(
        "kessler", [("kessler_run", params, "kessler")], _TOLERANCE, directive="acc",
    )
    assert "!$acc enter data create(precl)" in source
    assert "!$acc exit data copyout(precl)" in source
    assert "copyin(precl)" not in source


def test_multiple_device_arrays_grouped_into_one_directive_each():
    params = [
        TestDriverParam("ncol", "in", "integer", None, 0),
        TestDriverParam("theta", "inout", "real", "kind_phys", 1, dims=["ncol"], is_device=True),
        TestDriverParam("qv", "inout", "real", "kind_phys", 1, dims=["ncol"], is_device=True),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    source = render_scheme_io_capture_test_driver(
        "kessler", [("kessler_run", params, "kessler")], _TOLERANCE, directive="acc",
    )
    # One grouped directive, not one per array.
    assert source.count("!$acc enter data") == 1
    assert source.count("!$acc exit data") == 1
    assert "!$acc enter data copyin(theta, qv)" in source
    assert "!$acc exit data copyout(theta, qv)" in source


def test_omp_directive_uses_map_clauses_not_acc_syntax():
    params = [
        TestDriverParam("ncol", "in", "integer", None, 0),
        TestDriverParam("theta", "inout", "real", "kind_phys", 1, dims=["ncol"], is_device=True),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    source = render_scheme_io_capture_test_driver(
        "kessler", [("kessler_run", params, "kessler")], _TOLERANCE, directive="omp",
    )
    assert "!$omp target enter data map(to:theta)" in source
    assert "!$omp target exit data map(from:theta)" in source
    assert "!$acc" not in source


def test_no_directive_means_no_device_directive_text_at_all():
    # directive=None (the default) -- a device-resident arg still exists
    # in the metadata, but with no --directive at cap-generation time
    # there's no GPU build to support, so the driver must stay exactly
    # like a plain CPU-only one (no acc/omp text anywhere).
    params = [
        TestDriverParam("ncol", "in", "integer", None, 0),
        TestDriverParam("theta", "inout", "real", "kind_phys", 1, dims=["ncol"], is_device=True),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    source = render_scheme_io_capture_test_driver(
        "kessler", [("kessler_run", params, "kessler")], _TOLERANCE,
    )
    assert "!$acc" not in source
    assert "!$omp" not in source


def test_host_only_array_untouched_even_with_directive_set():
    # is_device=False (the default) -- a plain host array must never show
    # up in an enter/exit-data directive just because --directive was set
    # for the scheme overall; only its own memory_space=device arguments do.
    params = [
        TestDriverParam("ncol", "in", "integer", None, 0),
        TestDriverParam("precl", "out", "real", "kind_phys", 1, dims=["ncol"]),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    source = render_scheme_io_capture_test_driver(
        "kessler", [("kessler_run", params, "kessler")], _TOLERANCE, directive="acc",
    )
    assert "!$acc" not in source


def test_captured_array_without_dims_is_sized_from_the_capture_file():
    """A captured array whose size no argument carries (geopotential_temp's
    vertical_interface_dimension) is allocated to the captured shape:
    inputs from `in`, results from `out`."""
    params = [
        TestDriverParam("piln", "in", "real", "kind_phys", 2),
        TestDriverParam("zi", "out", "real", "kind_phys", 2),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    source = render_scheme_io_capture_test_driver(
        "geopotential_temp", [("geopotential_temp_run", params, "geopotential_temp")], _TOLERANCE,
    )
    assert "integer :: extents1(1), extents2(2), extents3(3)" in source
    assert 'call ccpp_capture_extents("in", "piln", extents2, extents_found)' in source
    assert "allocate(piln(extents2(1), extents2(2)))" in source
    # An out-only array and its expected copy take the `out` shape.
    assert 'call ccpp_capture_extents("out", "zi", extents2, extents_found)' in source
    assert "allocate(zi_expected(extents2(1), extents2(2)))" in source
    # Sized after the file is open, before the array is read.
    assert (source.index("call ccpp_capture_open_call")
            < source.index("allocate(piln(")
            < source.index('call ccpp_capture_read("in", "piln", piln)'))


def test_derived_type_argument_is_rebuilt_not_compared():
    params = [
        TestDriverParam("cprops", "in", "ccpp_constituent_prop_ptr_t", None, 1,
                        ddt_read="ccpp_capture_read_constituents",
                        ddt_read_module="ccpp_capture_constituents_mod",
                        type_module="ccpp_constituent_prop_mod"),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    source = render_scheme_io_capture_test_driver(
        "geopotential_temp", [("geopotential_temp_run", params, "geopotential_temp")], _TOLERANCE,
    )
    assert "  use ccpp_constituent_prop_mod, only: ccpp_constituent_prop_ptr_t\n" in source
    assert "  use ccpp_capture_constituents_mod, only: ccpp_capture_read_constituents\n" in source
    assert "type(ccpp_constituent_prop_ptr_t), allocatable :: cprops(:)" in source
    assert 'call ccpp_capture_read_constituents("in", "cprops", cprops)' in source
    assert "allocate(cprops" not in source  # the read allocates it
    assert "cprops_expected" not in source


def test_driver_uses_the_module_that_holds_the_scheme():
    """Several schemes can share one module (CAM-SIMA's state_converters):
    the driver uses the module the cap uses, not the scheme name."""
    params = [
        TestDriverParam("rho", "out", "real", "kind_phys", 2),
        TestDriverParam("errmsg", "error_arg", "character", "len=512", 0),
        TestDriverParam("errflg", "error_arg", "integer", None, 0),
    ]
    source = render_scheme_io_capture_test_driver(
        "calc_dry_air_ideal_gas_density",
        [("calc_dry_air_ideal_gas_density_run", params, "state_converters")], _TOLERANCE,
    )
    assert "  use state_converters, only: calc_dry_air_ideal_gas_density_run\n" in source
    assert "use calc_dry_air_ideal_gas_density," not in source
