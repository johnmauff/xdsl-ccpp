"""The scheme I/O capture test driver, built as IR by
capture_driver_ir.build_test_driver and printed by print_ftn
(scheme-io-capture-driver-as-ir). The checks are on the printed program's
statements (continuation lines joined), not its exact layout: replaying
every captured call in a loop (scheme-io-capture-multi-timestep), failure
diagnostics (scheme-io-capture-compare-diagnostics), the tolerance,
device copies (scheme-io-capture-gpu-residency), sizes from the capture
file, derived types, the log unit, the constituent table, call-only phases,
other real kinds and long calls.
"""

import io
import re

from xdsl_ccpp.backend.print_ftn import format_fortran_real_literal, print_fortran_unit
from xdsl_ccpp.transforms.capture_driver_ir import TestDriverParam as P
from xdsl_ccpp.transforms.capture_driver_ir import build_test_driver

_ERR = [P("errmsg", "error_arg", "character", "len=512", 0),
        P("errflg", "error_arg", "integer", None, 0)]


def _driver(phase_tables, tolerance=1e-10, directive=None, scheme="kessler") -> str:
    program = build_test_driver(scheme, phase_tables, tolerance, directive)
    program.verify()
    out = io.StringIO()
    print_fortran_unit(program, out)
    return re.sub(r",\s*&\n\s*", ", ", out.getvalue())  # join continuation lines


def _run(params, **kwargs) -> str:
    return _driver([("kessler_run", params + _ERR, "kessler")], **kwargs)


def _between(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i:text.index(end, i)]


def test_every_captured_call_is_replayed():
    source = _run([P("ncol", "in", "integer", None, 0),
                   P("theta", "inout", "real", "kind_phys", 2)])
    assert "n_calls = ccpp_capture_call_count('kessler_run')" in source
    assert "do call_count = 1, n_calls" in source
    loop = _between(source, "do call_count = 1, n_calls", "end do")
    assert "call ccpp_capture_open_call('kessler_run', call_count, found)" in loop
    # Inputs from the file's `in` group, results from `out`; the file is
    # closed before the compares.
    assert "call ccpp_capture_read('in', 'ncol', ncol)" in loop
    assert "call ccpp_capture_read('in', 'theta', theta)" in loop
    assert (loop.index("call ccpp_capture_read('out', 'theta', theta_expected)")
            < loop.index("call ccpp_capture_close()")
            < loop.index("ok = ccpp_capture_compare(theta, theta_expected, tolerance"))
    assert "call ccpp_capture_report('theta', call_count, ok, n_failed)" in loop
    # No captured call at all is a FAIL, not a vacuous pass.
    assert "if (n_calls .eq. 0) then" in source
    assert "write(*,*) 'FAIL: no captured calls of kessler_run found'" in source
    # The report is the library's, not a generated subroutine.
    assert "subroutine report" not in source


def test_arrays_are_reallocated_inside_the_loop():
    """A scheme's column count can differ call to call (chunks)."""
    source = _run([P("ncol", "in", "integer", None, 0), P("nz", "in", "integer", None, 0),
                   P("scratch", "unverified", "real", "r4", 2, dims=["ncol", "nz"])])
    loop = _between(source, "do call_count = 1, n_calls", "end do")
    assert "if (allocated(scratch)) deallocate(scratch)" in loop
    assert "allocate(scratch(ncol, nz))" in loop
    # Sized after ncol and nz are read.
    assert loop.index("call ccpp_capture_read('in', 'nz', nz)") < loop.index("allocate(scratch(")


def test_captured_arrays_take_the_captured_shape():
    """A captured array is sized from the file: inputs from `in`, results
    (and the expected copy) from `out`, after the file is open and before
    the read."""
    source = _run([P("piln", "in", "real", "kind_phys", 2), P("zi", "out", "real", "kind_phys", 2)])
    assert "integer :: extents2(2)" in source
    assert "call ccpp_capture_extents('in', 'piln', extents2, extents_found)" in source
    assert "allocate(piln(extents2(1), extents2(2)))" in source
    assert "call ccpp_capture_extents('out', 'zi', extents2, extents_found)" in source
    assert "allocate(zi_expected(extents2(1), extents2(2)))" in source
    assert (source.index("call ccpp_capture_open_call")
            < source.index("allocate(piln(")
            < source.index("call ccpp_capture_read('in', 'piln', piln)"))


def test_errflg_failure_names_the_call_and_message():
    source = _run([P("lv_in", "in", "real", "kind_phys", 0)])
    check = _between(source, "if (errflg .ne. 0) then", "end if")
    assert ("write(*,*) 'FAIL: kessler_run returned errflg=', errflg, ' (call ', call_count, ')', "
            "' errmsg=', trim(errmsg)") in check
    assert "n_failed = n_failed + 1" in check


def test_phases_share_their_declarations():
    init = [P("lv_in", "in", "real", "kind_phys", 0)] + _ERR
    run = [P("ncol", "in", "integer", None, 0)] + _ERR
    source = _driver([("kessler_init", init, "kessler"), ("kessler_run", run, "kessler")])
    for decl in ("integer :: call_count", "logical :: found", "integer :: errflg",
                 "character(len=512) :: errmsg"):
        assert source.count(decl) == 1, decl
    assert source.count("do call_count = 1, n_calls") == 2
    assert source.index("call kessler_init(") < source.index("call kessler_run(")


def test_scalar_compare_prints_both_values_on_failure():
    source = _run([P("out_var", "out", "integer", None, 0)])
    assert "ok = ccpp_capture_compare(out_var, out_var_expected)" in source
    failure = _between(source, "if (.NOT. (ok)) then", "end if")
    assert "write(*,*) '  actual=', out_var, ' expected=', out_var_expected" in failure


def test_array_compare_diagnostics():
    source = _run([P("ncol", "in", "integer", None, 0),
                   P("precl", "out", "real", "kind_phys", 1),
                   P("flags", "out", "logical", None, 1)])
    assert source.count("real(kind=kind_phys) :: diag_max_abs_diff") == 1
    assert source.count("integer :: diag_first_mismatch_index") == 1
    assert ("ok = ccpp_capture_compare(precl, precl_expected, tolerance, diag_max_abs_diff, "
            "diag_mean_abs_diff, diag_first_mismatch_index)") in source
    assert ("write(*,*) '  max abs diff=', diag_max_abs_diff, ' mean abs diff=', "
            "diag_mean_abs_diff, ' first mismatch at linear index=', "
            "diag_first_mismatch_index") in source
    # A logical array asks for the index only.
    assert "ok = ccpp_capture_compare(flags, flags_expected, diag_first_mismatch_index)" in source


def test_format_fortran_real_literal_always_has_a_decimal_point():
    assert format_fortran_real_literal(1e-10) == "1.0e-10_kind_phys"
    assert format_fortran_real_literal(0.001) == "0.001_kind_phys"
    assert format_fortran_real_literal(5.0) == "5.0_kind_phys"
    assert format_fortran_real_literal(-1e-10) == "-1.0e-10_kind_phys"
    assert format_fortran_real_literal(1e-8, kind="r8") == "1.0e-08_r8"


def test_tolerance_is_a_runtime_overridable_kind_phys_default():
    source = _run([P("precl", "out", "real", "kind_phys", 1)], tolerance=5e-6)
    assert "real(kind=kind_phys) :: tolerance" in source
    assert "parameter" not in source
    assert "tolerance = ccpp_capture_tolerance_override(5.0e-06_kind_phys)" in source
    assert "ccpp_capture_compare(precl, precl_expected, tolerance, " in source
    assert "ccpp_capture_tolerance_override(0.0_kind_phys)" in _run([], tolerance=0.0)


# Device copies (scheme-io-capture-gpu-residency): a driver has no
# surrounding residency, so a device argument is copied around the call,
# inside #ifdef USE_GPU as in the caps (the capture build defines USE_GPU
# with OpenACC).

def _device(params, directive="acc") -> str:
    return _run([P("ncol", "in", "integer", None, 0)] + params, directive=directive)


def test_inout_device_array_copied_in_and_out_around_the_call():
    source = _device([P("theta", "inout", "real", "kind_phys", 1, is_device=True)])
    assert "#ifdef USE_GPU\n      !$acc enter data copyin(theta)\n#endif" in source
    assert "#ifdef USE_GPU\n      !$acc exit data copyout(theta)\n#endif" in source
    assert "create(theta)" not in source and "delete(theta)" not in source
    # The result is copied back before it is compared.
    assert (source.index("enter data copyin(theta)") < source.index("call kessler_run(")
            < source.index("exit data copyout(theta)")
            < source.index("ccpp_capture_compare(theta, theta_expected"))


def test_in_only_device_array_is_deleted_not_copied_out():
    source = _device([P("cpair", "in", "real", "kind_phys", 1, is_device=True)])
    assert "!$acc enter data copyin(cpair)" in source
    assert "!$acc exit data delete(cpair)" in source
    assert "copyout(cpair)" not in source


def test_out_only_device_array_is_created_not_copied_in():
    source = _device([P("precl", "out", "real", "kind_phys", 1, is_device=True)])
    assert "!$acc enter data create(precl)" in source
    assert "!$acc exit data copyout(precl)" in source
    assert "copyin(precl)" not in source


def test_device_arrays_share_one_directive_each_way():
    source = _device([P("theta", "inout", "real", "kind_phys", 1, is_device=True),
                      P("qv", "inout", "real", "kind_phys", 1, is_device=True)])
    assert source.count("!$acc enter data") == 1 and source.count("!$acc exit data") == 1
    assert "!$acc enter data copyin(theta, qv)" in source
    assert "!$acc exit data copyout(theta, qv)" in source


def test_omp_directive_uses_map_clauses():
    source = _device([P("theta", "inout", "real", "kind_phys", 1, is_device=True)], "omp")
    assert "!$omp target enter data map(to:theta)" in source
    assert "!$omp target exit data map(from:theta)" in source
    assert "!$acc" not in source


def test_no_device_copies_without_a_directive_or_a_device_argument():
    no_directive = _device([P("theta", "inout", "real", "kind_phys", 1, is_device=True)], None)
    host_only = _device([P("precl", "out", "real", "kind_phys", 1)])
    for source in (no_directive, host_only):
        assert "!$acc" not in source and "!$omp" not in source and "USE_GPU" not in source


def test_derived_type_argument_is_rebuilt_not_compared():
    source = _run([P("cprops", "in", "ccpp_constituent_prop_ptr_t", None, 1,
                     ddt_read="ccpp_capture_read_constituents",
                     ddt_read_module="ccpp_capture_constituents_mod",
                     type_module="ccpp_constituent_prop_mod")])
    assert "  use ccpp_constituent_prop_mod, only: ccpp_constituent_prop_ptr_t\n" in source
    assert "  use ccpp_capture_constituents_mod, only: ccpp_capture_read_constituents\n" in source
    assert "type(ccpp_constituent_prop_ptr_t), allocatable :: cprops(:)" in source
    assert "call ccpp_capture_read_constituents('in', 'cprops', cprops)" in source
    assert "allocate(cprops" not in source  # the read allocates it
    assert "cprops_expected" not in source


def test_driver_uses_the_module_that_holds_the_scheme():
    """Several schemes can share a module (CAM-SIMA's state_converters)."""
    source = _driver([("calc_dry_air_ideal_gas_density_run",
                       [P("rho", "out", "real", "kind_phys", 2)] + _ERR, "state_converters")],
                     scheme="calc_dry_air_ideal_gas_density")
    assert "  use state_converters, only: calc_dry_air_ideal_gas_density_run\n" in source
    assert "use calc_dry_air_ideal_gas_density," not in source


def test_log_unit_is_standard_output_never_the_captured_unit():
    """scheme-io-capture-log-unit: the captured unit is the host's, not
    open in the driver."""
    source = _driver([("cloud_cover_init", [P("ncol", "in", "integer", None, 0),
                                             P("iulog", "log_unit", "integer", None, 0)] + _ERR,
                       "cloud_cover")])
    assert "  use ccpp_capture_mod, only: ccpp_capture_output_unit\n" in source
    assert "integer :: iulog" in source
    assert source.index("iulog = ccpp_capture_output_unit") < source.index("call cloud_cover_init(")
    assert "iulog=iulog" in source
    assert "'iulog'" not in source and "iulog_expected" not in source
    assert "iso_fortran_env" not in source


def test_constituent_table_restored_first():
    """scheme-io-capture-constituent-index-table."""
    params = [P("ncol", "in", "integer", None, 0)] + _ERR
    source = _driver([("s_init", params, "s"), ("s_run", params, "s")])
    assert "  use ccpp_capture_replay_mod, only: ccpp_capture_restore_constituents\n" in source
    assert source.count("call ccpp_capture_restore_constituents()") == 1
    assert (source.index("call ccpp_capture_restore_constituents()")
            < source.index("ccpp_capture_open_call('s_init'"))


def test_call_only_phase_called_once_before_the_compared_phase():
    """scheme-io-capture-uncaptured-phases."""
    init = [P("iulog", "log_unit", "integer", None, 0)] + _ERR
    run = [P("ncol", "in", "integer", None, 0)] + _ERR
    source = _driver([("s_init", init, "s"), ("s_run", run, "s")])
    init_call = source.index("call s_init(iulog=iulog, errmsg=errmsg, errflg=errflg)")
    assert source.index("iulog = ccpp_capture_output_unit") < init_call
    assert init_call < source.index("ccpp_capture_open_call('s_run'")
    assert "ccpp_capture_open_call('s_init'" not in source
    assert "ccpp_capture_call_count('s_init')" not in source
    assert "FAIL: s_init returned errflg=" in source


def test_other_real_kinds_come_from_ccpp_kinds():
    """scheme-io-capture-real-kinds."""
    source = _run([P("x", "inout", "real", "pumas_r8", 2), P("y", "out", "real", "kind_phys", 2)])
    assert "  use ccpp_kinds, only: pumas_r8\n" in source
    assert "  use ccpp_kinds, only: kind_phys\n" in source
    assert "real(kind=pumas_r8), allocatable :: x(:, :)" in source
    assert "pumas_r8" not in _run([P("y", "out", "real", "kind_phys", 2)])


def test_long_scheme_call_is_continued():
    """micro_pumas_ccpp_dimensions_post: ~140 arguments."""
    params = [P("ncol", "in", "integer", None, 0)] + [
        P(f"field_{i:03d}", "out", "real", "kind_phys", 2) for i in range(140)]
    program = build_test_driver("s", [("s_run", params, "s")], 0.0)
    out = io.StringIO()
    print_fortran_unit(program, out)
    assert max(len(line) for line in out.getvalue().splitlines()) <= 99
    call = "call s_run(" + ", ".join(
        ["ncol=ncol"] + [f"field_{i:03d}=field_{i:03d}" for i in range(140)]) + ")"
    joined = re.sub(r"\s*&\n\s*", " ", out.getvalue()).replace("( ", "(").replace(",  ", ", ")
    assert call in joined


def test_program_layout():
    source = _run([P("ncol", "in", "integer", None, 0)])
    lines = source.splitlines()
    assert lines[0].startswith("! Generated by xdsl_ccpp")
    assert "program test_kessler" in lines and lines[-1] == "end program test_kessler"
    assert "  call test_kessler_main()" in lines
    assert "    if (n_failed .eq. 0) then" in lines
    assert "      write(*,*) 'ALL TESTS PASSED'" in lines
    assert "      write(*,*) n_failed, ' TEST(S) FAILED'" in lines
    assert "      call exit(1)" in lines


def test_uncaptured_derived_type_is_declared_with_its_type():
    """A derived type outside the capture's scope (RRTMGP's ty_gas_concs_ccpp)
    is declared as itself, passed, and never read or compared."""
    source = _run([P("gas_concs", "unverified", "ty_gas_concs_ccpp", None, 0)])
    assert "type(ty_gas_concs_ccpp) :: gas_concs" in source
    assert "gas_concs=gas_concs" in source
    assert "'gas_concs'" not in source
