"""Unit tests for `--capture-scheme` (SchemeIOCapturePass).

scheme-io-capture (BACKLOG.md), NetCDF format (scheme-io-capture-netcdf):
each captured scheme call gets `ccpp_capture_begin(table, 'before')`, one
`ccpp_capture(name, value, standard_name, units, dim_names)` per argument
and `ccpp_capture_end()` before the call, and the same with 'after' after
it. These tests assert on the generated call *text* and *position*, not a
real compile. Same harness/style as
test_gpu_debug_sync.py/test_gpu_directives.py/test_gpu_debug_print_pass.py:
synthetic .meta/suite-XML fixtures run through the real pipeline, sliced
subroutine-body text, substring/position/count assertions.
"""

from io import StringIO

import pytest

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.gpu_ccpp_cap_pass import GPUCcppCapPass
from xdsl_ccpp.transforms.gpu_data_pass import GPUDataPass
from xdsl_ccpp.transforms.scheme_io_capture_pass import (
    SchemeIOCapturePass,
    _is_capture_supported,
)
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

pytestmark = pytest.mark.usefixtures("legacy_mode")

# Covers every v1-relevant shape in one scheme, two entry points:
#  - in_var:    intent=in, real(kind_phys)   -> one capture, before only.
#  - out_var:   intent=out, integer          -> one capture, after only.
#  - io_var:    intent=inout, real(kind_phys), device-resident, rank 2
#               -> two captures (before + after), each preceded by a sync.
#  - skip_opt:  intent=in, optional          -> never captured.
#  - skip_str:  type=character, intent=in    -> captured before (character
#               values are supported since the NetCDF format; the name is
#               historical).
# errmsg/errflg come from CCPP_MANDATORY_ARGS and must never be captured.
_SCHEME_META = f"""\
[ccpp-table-properties]
  name = test_io_capture_scheme
  type = scheme
[ccpp-arg-table]
  name = test_io_capture_scheme_run
  type = scheme
[ in_var ]
  standard_name = test_capture_in_var
  units = K
  type = real | kind = kind_phys
  dimensions = ()
  intent = in
[ out_var ]
  standard_name = test_capture_out_var
  units = count
  type = integer
  dimensions = ()
  intent = out
[ io_var ]
  standard_name = test_capture_io_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = inout
[ skip_opt ]
  standard_name = test_capture_skip_opt
  units = K
  type = real | kind = kind_phys
  dimensions = ()
  intent = in
  optional = .true.
[ skip_str ]
  standard_name = test_capture_skip_str
  units = none
  type = character
  kind = len=64
  dimensions = ()
  intent = in
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = test_io_capture_scheme_init
  type = scheme
[ in_var ]
  standard_name = test_capture_in_var
  units = K
  type = real | kind = kind_phys
  dimensions = ()
  intent = in
{CCPP_MANDATORY_ARGS}
"""

_HOST_META = """\
[ccpp-table-properties]
  name = test_io_capture_host
  type = module
[ccpp-arg-table]
  name = test_io_capture_host
  type = module
[ in_var ]
  standard_name = test_capture_in_var
  units = K
  type = real | kind = kind_phys
  dimensions = ()
[ out_var ]
  standard_name = test_capture_out_var
  units = count
  type = integer
  dimensions = ()
[ io_var ]
  standard_name = test_capture_io_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
[ skip_str ]
  standard_name = test_capture_skip_str
  units = none
  type = character
  kind = len=64
  dimensions = ()
"""

_SUITE_XML = minimal_suite_xml("test_io_capture_scheme", suite_name="test_io_capture_suite")


def _fortran_output(run_host_match, ccpp_context, scheme="", phase="", directive=None,
                    test_driver_dir=None) -> str:
    module = run_host_match(
        scheme_metas=[_SCHEME_META],
        host_metas=[_HOST_META],
        suite_xml=_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    if directive:
        GPUDataPass(directive=directive).apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    if directive:
        GPUCcppCapPass(directive=directive).apply(ccpp_context, module)
    SchemeIOCapturePass(
        scheme=scheme, phase=phase, directive=directive, test_driver_dir=test_driver_dir,
    ).apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def test_no_effect_when_scheme_unset(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="")
    assert "ccpp_capture_" not in fortran


def test_no_effect_for_unmatched_scheme_name(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="nonexistent_scheme")
    assert "ccpp_capture_" not in fortran


_RUN = "test_io_capture_scheme_run"
_BEGIN_BEFORE = f"call ccpp_capture_begin('{_RUN}', 'before')"
_BEGIN_AFTER = f"call ccpp_capture_begin('{_RUN}', 'after')"
_SCHEME_CALL = f"call {_RUN}("


def _block(fortran: str, begin: str) -> str:
    """The text from `begin` to the next ccpp_capture_end()."""
    start = fortran.index(begin)
    return fortran[start:fortran.index("call ccpp_capture_end()", start)]


def test_intent_in_scalar_captured_before_only(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    capture = "call ccpp_capture('in_var', in_var, 'test_capture_in_var', 'K', '')"
    assert capture in _block(fortran, _BEGIN_BEFORE)
    assert "'in_var'" not in _block(fortran, _BEGIN_AFTER)
    assert fortran.index(_BEGIN_BEFORE) < fortran.index(_SCHEME_CALL)


def test_intent_out_scalar_captured_after_only(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    capture = "call ccpp_capture('out_var', out_var, 'test_capture_out_var', 'count', '')"
    assert capture in _block(fortran, _BEGIN_AFTER)
    assert "'out_var'" not in _block(fortran, _BEGIN_BEFORE)
    assert fortran.index(_SCHEME_CALL) < fortran.index(_BEGIN_AFTER)


def test_before_and_after_blocks_frame_the_call(run_host_match, ccpp_context):
    """begin/end pairs are emitted around every captured call, even with
    nothing to write on one side (init has no outputs): 'before' opens
    and counts the call's file, 'after' reopens it."""
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    init_after = "call ccpp_capture_begin('test_io_capture_scheme_init', 'after')"
    assert init_after in fortran
    # init + run, before + after, plus the constituent table (once)
    assert fortran.count("call ccpp_capture_end()") == 5
    for procedure in ("ccpp_capture", "ccpp_capture_begin", "ccpp_capture_end"):
        assert f"use ccpp_capture_mod, only: {procedure}\n" in fortran


def test_driver_dir_becomes_the_capture_directory(run_host_match, ccpp_context, tmp_path):
    """With a driver directory, each "before" block first points the
    runtime at it (ccpp_capture_set_dir), so data and drivers share it."""
    fortran = _fortran_output(
        run_host_match, ccpp_context, scheme="test_io_capture_scheme",
        test_driver_dir=str(tmp_path),
    )
    set_dir = "call ccpp_capture_set_dir("
    # init + run, "before" only, plus the constituent table
    assert fortran.count(set_dir) == 3
    assert fortran.count(f"'{tmp_path}')") == 3
    init_after = fortran.index("call ccpp_capture_begin('test_io_capture_scheme_init', 'after')")
    assert fortran.index(set_dir, init_after) < fortran.index(_BEGIN_BEFORE) < fortran.index(_SCHEME_CALL)
    assert "use ccpp_capture_mod, only: ccpp_capture_set_dir\n" in fortran


def test_label_names_the_data_subdirectory(run_host_match, ccpp_context, tmp_path):
    module = run_host_match(
        scheme_metas=[_SCHEME_META], host_metas=[_HOST_META], suite_xml=_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    SchemeIOCapturePass(
        scheme="test_io_capture_scheme", test_driver_dir=str(tmp_path), label="case.c01b",
    ).apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    fortran = out.getvalue()

    assert (tmp_path / "case.c01b").is_dir()
    # The caps name the driver dir; the runtime appends the label.
    assert fortran.count(f"'{tmp_path}')") == 3  # + the constituent table
    assert fortran.count("call ccpp_capture_set_info('case.c01b', 'xdsl_ccpp") == 3
    # The drivers stay in the driver directory itself.
    assert (tmp_path / "test_test_io_capture_scheme.F90").exists()


def test_set_info_records_generator_in_each_before_block(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    set_info = "call ccpp_capture_set_info('', 'xdsl_ccpp"
    assert fortran.count(set_info) == 3  # init + run + the constituent table
    assert fortran.index(set_info, fortran.index(
        "call ccpp_capture_begin('test_io_capture_scheme_init', 'after')")) < fortran.index(_BEGIN_BEFORE)
    # This host has no current_timestep_number: no attribute call.
    assert "ccpp_capture_attribute" not in fortran


def test_no_set_dir_without_driver_dir(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    assert "ccpp_capture_set_dir" not in fortran


def test_intent_inout_array_captured_both_with_device_sync(run_host_match, ccpp_context):
    fortran = _fortran_output(
        run_host_match, ccpp_context, scheme="test_io_capture_scheme", directive="acc",
    )
    # Metadata dimension names name the file's dimensions.
    io_capture = "'horizontal_loop_extent,vertical_layer_dimension')"
    assert "'io_var', io_var, 'test_capture_io_var', 'K'" in _block(fortran, _BEGIN_BEFORE)
    assert io_capture in _block(fortran, _BEGIN_BEFORE)
    assert "'io_var', io_var" in _block(fortran, _BEGIN_AFTER)
    # A device-resident arg is synced to the host before each block.
    assert fortran.count("update self(io_var)") == 2
    call_pos = fortran.index(_SCHEME_CALL)
    before_sync_pos = fortran.rindex("update self(io_var)", 0, call_pos)
    assert before_sync_pos < fortran.index(_BEGIN_BEFORE) < call_pos
    after_pos = fortran.index(_BEGIN_AFTER)
    after_sync_pos = fortran.rindex("update self(io_var)", call_pos, after_pos)
    assert call_pos < after_sync_pos < after_pos


def test_no_device_sync_without_directive(run_host_match, ccpp_context):
    # Same io_var, but no --directive at all -- there's no GPU residency
    # to sync, so no update self(...) should appear even though io_var is
    # declared memory_space=device.
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    assert "update self(io_var)" not in fortran
    assert "'io_var', io_var" in _block(fortran, _BEGIN_BEFORE)


def test_optional_argument_never_captured(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    assert "'skip_opt'" not in fortran


def test_character_argument_captured(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    assert ("call ccpp_capture('skip_str', skip_str, 'test_capture_skip_str', 'none', '')"
            in _block(fortran, _BEGIN_BEFORE))


@pytest.mark.parametrize("arg_type, kind, rank, supported", [
    ("real", "kind_phys", 3, True),
    ("real", "kind_phys", 4, False),
    ("real", "kind_r4", 1, False),
    ("integer", None, 0, True),
    ("logical", None, 2, True),
    ("character", "len=64", 0, True),
    ("character", "len=64", 1, True),
    ("character", "len=64", 2, False),
    ("ccpp_constituent_prop_ptr_t", None, 1, False),
])
def test_capture_type_scope(arg_type, kind, rank, supported):
    assert _is_capture_supported(arg_type, kind, rank) is supported


def test_errmsg_errflg_never_captured(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    assert "'errmsg'" not in fortran
    assert "'errflg'" not in fortran


def test_phase_filter_restricts_to_one_entry_point(run_host_match, ccpp_context):
    fortran = _fortran_output(
        run_host_match, ccpp_context, scheme="test_io_capture_scheme", phase="run",
    )
    assert _BEGIN_BEFORE in fortran
    assert "'test_io_capture_scheme_init'" not in fortran


def test_no_phase_filter_captures_every_entry_point(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    assert _BEGIN_BEFORE in fortran
    assert "call ccpp_capture_begin('test_io_capture_scheme_init', 'before')" in fortran


# Separate fixture (not the shared _HOST_META above) so the existing
# tests above keep covering the real "host declares no mpi-root flag at
# all" case (e.g. examples/kessler's own host) untouched, while these two
# tests cover the opposite, newly-added case (CAM-SIMA's own real
# convention: spmd_utils.F90's masterproc, standard_name
# flag_for_mpi_root) in isolation.
_HOST_META_WITH_MPI_ROOT = _HOST_META + """\
[ masterproc ]
  standard_name = flag_for_mpi_root
  units = flag
  type = logical
  dimensions = ()
"""


def test_capture_guarded_by_host_mpi_root_flag(run_host_match, ccpp_context):
    """When the host declares flag_for_mpi_root (CAM-SIMA's own real
    convention, backed by spmd_utils.F90's masterproc), every capture
    call must be guarded by it -- confirmed necessary against a real
    24-task CAM-SIMA build, where every task raced to write the same
    capture file and corrupted it."""
    module = run_host_match(
        scheme_metas=[_SCHEME_META],
        host_metas=[_HOST_META_WITH_MPI_ROOT],
        suite_xml=_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    SchemeIOCapturePass(scheme="test_io_capture_scheme").apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    fortran = out.getvalue()

    assert "use test_io_capture_host, only: masterproc" in fortran
    # The guard wraps the whole begin ... end block.
    begin_idx = fortran.index(_BEGIN_BEFORE)
    guard_idx = fortran.rindex("if (masterproc) then", 0, begin_idx)
    end_idx = fortran.index("call ccpp_capture_end()", begin_idx)
    end_if_idx = fortran.index("end if", begin_idx)
    assert guard_idx < begin_idx < end_idx < end_if_idx
    assert "'in_var', in_var" in fortran[begin_idx:end_idx]


_HOST_META_WITH_STEP = _HOST_META + """\
[ nstep ]
  standard_name = current_timestep_number
  units = count
  type = integer
  dimensions = ()
"""


def test_host_timestep_number_recorded_in_before_file(run_host_match, ccpp_context):
    """A host with current_timestep_number (CAM-SIMA's nstep) gets it
    written into each call's file, so a capture can be matched to its
    model step."""
    module = run_host_match(
        scheme_metas=[_SCHEME_META], host_metas=[_HOST_META_WITH_STEP], suite_xml=_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    SchemeIOCapturePass(scheme="test_io_capture_scheme").apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    fortran = out.getvalue()

    attribute = "call ccpp_capture_attribute('current_timestep_number', nstep)"
    assert "use test_io_capture_host, only: nstep" in fortran
    assert "use ccpp_capture_mod, only: ccpp_capture_attribute" in fortran
    assert attribute in _block(fortran, _BEGIN_BEFORE)
    assert attribute not in _block(fortran, _BEGIN_AFTER)


def test_no_guard_when_host_lacks_mpi_root_flag(run_host_match, ccpp_context):
    """The existing shared _HOST_META fixture never declares
    flag_for_mpi_root -- captures must remain unconditional there,
    exactly as before this guard existed (matches examples/kessler's own
    real host, which has no such concept and is single-process anyway)."""
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    assert "if (masterproc)" not in fortran
    assert "flag_for_mpi_root" not in fortran


# scheme-io-capture-tolerance-config: end-to-end through the real pass,
# not just render_scheme_io_capture_test_driver in isolation (that's
# already covered by test_print_ftn_scheme_io_capture_driver.py) --
# confirms the full chain self.tolerance (a string, set from the CLI's
# --capture-tolerance) -> float() -> format_fortran_real_literal() ->
# embedded literal in the written test_<scheme>.F90 file actually wires
# up correctly end to end.
def test_tolerance_option_reaches_the_written_test_driver_file(
    run_host_match, ccpp_context, tmp_path,
):
    module = run_host_match(
        scheme_metas=[_SCHEME_META],
        host_metas=[_HOST_META],
        suite_xml=_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    SchemeIOCapturePass(
        scheme="test_io_capture_scheme",
        test_driver_dir=str(tmp_path),
        tolerance="1e-6",
    ).apply(ccpp_context, module)

    driver_path = tmp_path / "test_test_io_capture_scheme.F90"
    assert driver_path.exists()
    driver_source = driver_path.read_text()
    assert "tolerance = ccpp_capture_tolerance_override(1.0e-06_kind_phys)" in driver_source


def test_default_tolerance_used_when_option_unset(run_host_match, ccpp_context, tmp_path):
    module = run_host_match(
        scheme_metas=[_SCHEME_META],
        host_metas=[_HOST_META],
        suite_xml=_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    SchemeIOCapturePass(
        scheme="test_io_capture_scheme",
        test_driver_dir=str(tmp_path),
    ).apply(ccpp_context, module)

    driver_path = tmp_path / "test_test_io_capture_scheme.F90"
    driver_source = driver_path.read_text()
    assert "tolerance = ccpp_capture_tolerance_override(0.0_kind_phys)" in driver_source


# scheme-io-capture-gpu-residency: a separate, dedicated fixture (not the
# shared _SCHEME_META/_HOST_META above) because io_var's own dims there
# (horizontal_loop_extent, vertical_layer_dimension) aren't resolvable to
# any scalar argument actually present in that scheme's own arg table --
# test-driver generation silently skips that call site entirely
# (_build_test_driver_params returns None), so io_var's device-sync
# behavior in the capture CALLS is covered above, but it never reaches a
# generated DRIVER there. This fixture adds the one resolvable scalar
# (ncol) io_var's own dims need, so the driver actually gets emitted.
_GPU_SCHEME_META = f"""\
[ccpp-table-properties]
  name = test_io_capture_gpu_scheme
  type = scheme
[ccpp-arg-table]
  name = test_io_capture_gpu_scheme_run
  type = scheme
[ ncol ]
  standard_name = horizontal_loop_extent
  units = count
  type = integer
  dimensions = ()
  intent = in
[ io_var ]
  standard_name = test_capture_gpu_io_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent)
  memory_space = device
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_GPU_HOST_META = """\
[ccpp-table-properties]
  name = test_io_capture_gpu_host
  type = module
[ccpp-arg-table]
  name = test_io_capture_gpu_host
  type = module
[ ncol ]
  standard_name = horizontal_loop_extent
  units = count
  type = integer
  dimensions = ()
[ io_var ]
  standard_name = test_capture_gpu_io_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent)
  memory_space = device
"""

_GPU_SUITE_XML = minimal_suite_xml(
    "test_io_capture_gpu_scheme", suite_name="test_io_capture_gpu_suite",
)


def test_gpu_residency_device_array_reaches_written_driver(run_host_match, ccpp_context, tmp_path):
    module = run_host_match(
        scheme_metas=[_GPU_SCHEME_META],
        host_metas=[_GPU_HOST_META],
        suite_xml=_GPU_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    GPUDataPass(directive="acc").apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    GPUCcppCapPass(directive="acc").apply(ccpp_context, module)
    SchemeIOCapturePass(
        scheme="test_io_capture_gpu_scheme",
        directive="acc",
        test_driver_dir=str(tmp_path),
    ).apply(ccpp_context, module)

    driver_path = tmp_path / "test_test_io_capture_gpu_scheme.F90"
    assert driver_path.exists()
    driver_source = driver_path.read_text()
    assert "!$acc enter data copyin(io_var)" in driver_source
    assert "!$acc exit data copyout(io_var)" in driver_source


def test_gpu_residency_defaults_to_openacc_without_directive(run_host_match, ccpp_context, tmp_path):
    # Same device-resident scheme, but no --directive at generation time
    # (a CPU capture): the driver still carries OpenACC data directives --
    # comments in a CPU build -- so the same capture replays on a GPU.
    module = run_host_match(
        scheme_metas=[_GPU_SCHEME_META],
        host_metas=[_GPU_HOST_META],
        suite_xml=_GPU_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    SchemeIOCapturePass(
        scheme="test_io_capture_gpu_scheme",
        test_driver_dir=str(tmp_path),
    ).apply(ccpp_context, module)

    driver_path = tmp_path / "test_test_io_capture_gpu_scheme.F90"
    driver_source = driver_path.read_text()
    assert "!$acc enter data copyin(io_var)" in driver_source
    assert "!$acc exit data copyout(io_var)" in driver_source
    assert "!$omp" not in driver_source


def test_wrap_paren_list_puts_an_overlong_item_on_its_own_line():
    """An item longer than a line (a long path literal) must not leave an
    empty continuation line before it (`&` alone ends the statement)."""
    from xdsl_ccpp.backend.print_ftn import wrap_paren_list

    item = "'" + "x" * 120 + "'"
    lines = wrap_paren_list("call f(", [item], ")", 99, "    ")
    assert lines == ["call f( &", "    " + item + ")"]


def test_long_line_splitter_never_leaves_a_lone_ampersand():
    """A comma followed only by the line's own trailing `&` is not a split
    point: the continuation line would hold nothing but `&`."""
    from xdsl_ccpp.backend.print_ftn import ftnPrintContext

    out = StringIO()
    ctx = ftnPrintContext(out)
    ctx.print("              '" + "x" * 85 + "', &")
    ctx.print("              'y')")
    lines = out.getvalue().splitlines()
    assert all(line.strip() != "&" for line in lines), lines


# A scheme taking the constituent properties (as geopotential_temp does):
# the framework provides ccpp_constituent_properties.
_CPROPS_SCHEME_META = f"""\
[ccpp-table-properties]
  name = test_io_capture_scheme
  type = scheme
[ccpp-arg-table]
  name = test_io_capture_scheme_run
  type = scheme
[ in_var ]
  standard_name = test_capture_in_var
  units = K
  type = real | kind = kind_phys
  dimensions = ()
  intent = in
[ cprops ]
  standard_name = ccpp_constituent_properties
  units = none
  type = ccpp_constituent_prop_ptr_t
  dimensions = (number_of_ccpp_constituents)
  intent = in
{CCPP_MANDATORY_ARGS}
"""


# Here the host declares them (CAM-SIMA's framework provides them).
_CPROPS_HOST_META = _HOST_META + """\
[ ncnst ]
  standard_name = number_of_ccpp_constituents
  units = count
  type = integer
  dimensions = ()
[ cprops ]
  standard_name = ccpp_constituent_properties
  units = none
  type = ccpp_constituent_prop_ptr_t
  dimensions = (number_of_ccpp_constituents)
"""


def _cprops_output(run_host_match, ccpp_context, test_driver_dir=None):
    module = run_host_match(
        scheme_metas=[_CPROPS_SCHEME_META], host_metas=[_CPROPS_HOST_META], suite_xml=_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    SchemeIOCapturePass(
        scheme="test_io_capture_scheme", test_driver_dir=test_driver_dir,
    ).apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def test_constituent_properties_captured_as_a_subgroup(run_host_match, ccpp_context):
    """A ccpp_constituent_prop_ptr_t argument goes to its own capture
    procedure (ccpp_capture_constituents_mod), in the "before" block only."""
    fortran = _cprops_output(run_host_match, ccpp_context)
    before = _block(fortran, _BEGIN_BEFORE)
    assert "call ccpp_capture_constituents('cprops', " in before
    assert "ccpp_capture_constituents" not in _block(fortran, _BEGIN_AFTER)
    assert "use ccpp_capture_constituents_mod, only: ccpp_capture_constituents\n" in fortran
    # Not through the generic writer.
    assert "call ccpp_capture('cprops'" not in fortran


def test_constituent_properties_rebuilt_in_the_driver(run_host_match, ccpp_context, tmp_path):
    _cprops_output(run_host_match, ccpp_context, test_driver_dir=str(tmp_path))
    driver = (tmp_path / "test_test_io_capture_scheme.F90").read_text()
    assert "use ccpp_constituent_prop_mod, only: ccpp_constituent_prop_ptr_t\n" in driver
    assert "use ccpp_capture_constituents_mod, only: ccpp_capture_read_constituents\n" in driver
    assert "type(ccpp_constituent_prop_ptr_t), allocatable :: cprops(:)" in driver
    assert 'call ccpp_capture_read_constituents("in", "cprops", cprops)' in driver
    assert "cprops=cprops" in driver
    assert "cprops_expected" not in driver  # rebuilt, never compared


@pytest.mark.parametrize("intent, rank", [("out", 1), ("inout", 1), ("in", 0)])
def test_constituent_properties_only_rank_one_intent_in(intent, rank):
    from xdsl_ccpp.transforms.scheme_io_capture_pass import _ddt_capture

    class _Arg:
        attrs = {"type": "ccpp_constituent_prop_ptr_t", "dimensions": rank, "intent": intent}

        def hasAttr(self, name):
            return name in self.attrs

        def getAttr(self, name):
            return self.attrs[name]

    assert _ddt_capture(_Arg()) is None


def test_driver_uses_the_schemes_own_module(run_host_match, ccpp_context, tmp_path):
    """A scheme in a module of another name (CAM-SIMA's state_converters
    holds several): the driver uses the module the cap uses."""
    meta = _SCHEME_META.replace(
        "  name = test_io_capture_scheme\n  type = scheme\n",
        "  name = test_io_capture_scheme\n  type = scheme\n  module_name = shared_converters\n",
        1,
    )
    module = run_host_match(scheme_metas=[meta], host_metas=[_HOST_META], suite_xml=_SUITE_XML)
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    SchemeIOCapturePass(
        scheme="test_io_capture_scheme", test_driver_dir=str(tmp_path),
    ).apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    assert "use shared_converters, only: test_io_capture_scheme_run" in out.getvalue()
    driver = (tmp_path / "test_test_io_capture_scheme.F90").read_text()
    assert "  use shared_converters, only: test_io_capture_scheme_run\n" in driver
    assert "use test_io_capture_scheme," not in driver


def test_assumed_length_character_argument_captured(run_host_match, ccpp_context):
    """A character(len=*) argument (qneg's print_qneg_warn and subnam)
    reaches the call through a cast; the variable behind it is captured."""
    meta = _SCHEME_META.replace(
        "  kind = len=64\n  dimensions = ()\n  intent = in",
        "  kind = len=*\n  dimensions = ()\n  intent = in", 1,
    )
    assert meta != _SCHEME_META
    module = run_host_match(scheme_metas=[meta], host_metas=[_HOST_META], suite_xml=_SUITE_XML)
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    SchemeIOCapturePass(scheme="test_io_capture_scheme").apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    assert "'skip_str', skip_str" in _block(out.getvalue(), _BEGIN_BEFORE)


def test_phase_list_captures_each_listed_entry_point(run_host_match, ccpp_context):
    """phase="initialize,run": both entry points (qneg:initialize,run leaves
    out the phases a driver cannot replay)."""
    fortran = _fortran_output(run_host_match, ccpp_context,
                              scheme="test_io_capture_scheme", phase="initialize,run")
    assert "call ccpp_capture_begin('test_io_capture_scheme_init', 'before')" in fortran
    assert "call ccpp_capture_begin('test_io_capture_scheme_run', 'before')" in fortran
    fortran = _fortran_output(run_host_match, ccpp_context,
                              scheme="test_io_capture_scheme", phase="run,finalize")
    assert "ccpp_capture_begin('test_io_capture_scheme_init'" not in fortran


def test_driver_device_args_reach_only_the_driver(run_host_match, ccpp_context, tmp_path):
    # Without --directive and with no memory_space in .meta, ccpp_dsl passes
    # the source's device arguments for the driver alone: the driver gets
    # enter/exit data, the cap gets no sync.
    meta = _GPU_SCHEME_META.replace("  memory_space = device\n", "")
    host = _GPU_HOST_META.replace("  memory_space = device\n", "")
    module = run_host_match(scheme_metas=[meta], host_metas=[host], suite_xml=_GPU_SUITE_XML)
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    SchemeIOCapturePass(
        scheme="test_io_capture_gpu_scheme",
        test_driver_dir=str(tmp_path),
        driver_device_args="test_io_capture_gpu_scheme_run:IO_VAR,other_run:ncol",
    ).apply(ccpp_context, module)

    driver_source = (tmp_path / "test_test_io_capture_gpu_scheme.F90").read_text()
    assert "!$acc enter data copyin(io_var)" in driver_source
    assert "!$acc exit data copyout(io_var)" in driver_source
    assert "copyin(ncol" not in driver_source  # another table's entry
    from xdsl_ccpp.dialects.ccpp_utils import AccUpdateSelfOp

    assert not any(isinstance(o, AccUpdateSelfOp) for o in module.walk())


@pytest.mark.parametrize("std_name, intent, expected", [
    ("log_output_unit", "in", "log_unit"),
    ("log_output_unit", "inout", "log_unit"),
    ("horizontal_loop_extent", "in", "in"),
])
def test_log_output_unit_gets_its_own_driver_category(std_name, intent, expected):
    """scheme-io-capture-log-unit: the host's log unit is replaced in the
    driver, whatever its intent, so it is never read back or compared."""
    from xdsl_ccpp.transforms.scheme_io_capture_pass import _driver_param_category

    class _Arg:
        attrs = {"type": "integer", "dimensions": 0, "intent": intent,
                 "standard_name": std_name}

        def hasAttr(self, name):
            return name in self.attrs

        def getAttr(self, name):
            return self.attrs[name]

    assert _driver_param_category(_Arg()) == expected



_TABLE_BEGIN = "call ccpp_capture_begin('ccpp_constituents', 'before')"
_TABLE_WRITE = "call ccpp_capture_constituents('constituents', lc_const_props)"


def test_constituent_table_captured_once_where_the_cap_fills_it(run_host_match, ccpp_context):
    """scheme-io-capture-constituent-index-table: the host cap's
    constituent-properties array is captured once, right after the cap
    fills it and before it is handed to ccpp_scheme_utils, so a driver can
    answer the scheme's ccpp_constituent_index lookups as the run did."""
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    assert fortran.count(_TABLE_BEGIN) == 1
    assert fortran.count(_TABLE_WRITE) == 1
    fill = fortran.index("lc_const_props = lc_props_ptr")
    table = fortran.index(_TABLE_BEGIN)
    handed = fortran.index("call ccpp_scheme_utils_set_constituents(lc_const_props)")
    assert fill < fortran.index("call ccpp_capture_set_info(", fill) < table
    assert table < fortran.index(_TABLE_WRITE) < fortran.index("call ccpp_capture_end()", table) < handed
    assert "use ccpp_capture_constituents_mod, only: ccpp_capture_constituents\n" in fortran


def test_constituent_table_captured_once_for_several_schemes(run_host_match, ccpp_context):
    """One pass instance runs per --capture-scheme entry; only the first
    inserts the table capture."""
    module = run_host_match(
        scheme_metas=[_SCHEME_META], host_metas=[_HOST_META], suite_xml=_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    for phase in ("init", "run"):
        SchemeIOCapturePass(scheme="test_io_capture_scheme", phase=phase).apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    assert out.getvalue().count(_TABLE_BEGIN) == 1


def test_constituent_table_capture_guarded_by_host_mpi_root_flag(run_host_match, ccpp_context):
    module = run_host_match(
        scheme_metas=[_SCHEME_META], host_metas=[_HOST_META_WITH_MPI_ROOT], suite_xml=_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    SchemeIOCapturePass(scheme="test_io_capture_scheme").apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    fortran = out.getvalue()
    table = fortran.index(_TABLE_BEGIN)
    guard = fortran.rindex("if (masterproc) then", 0, table)
    assert fortran.index("lc_const_props = lc_props_ptr") < guard
    assert table < fortran.index("end if", table)


def test_no_constituent_table_capture_when_nothing_is_captured(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="nonexistent_scheme")
    assert "ccpp_constituents" not in fortran


# scheme-io-capture-uncaptured-phases: the init table with nothing to
# capture -- only errmsg/errflg (clamp_number_concentrations_init).
_INIT_IN_VAR = """[ in_var ]
  standard_name = test_capture_in_var
  units = K
  type = real | kind = kind_phys
  dimensions = ()
  intent = in
{CCPP_MANDATORY_ARGS}
"""
_INIT_TABLE_HEAD = "  name = test_io_capture_scheme_init\n  type = scheme\n"


def _driver_with_init(run_host_match, ccpp_context, tmp_path, init_args: str, phase: str = ""):
    """Write the driver for _SCHEME_META with its init table's arguments
    replaced by *init_args*; returns (cap Fortran, driver text or None)."""
    head, init = _SCHEME_META.split(_INIT_TABLE_HEAD)
    assert init == _INIT_IN_VAR.format(CCPP_MANDATORY_ARGS=CCPP_MANDATORY_ARGS)
    meta = head + _INIT_TABLE_HEAD + init_args
    module = run_host_match(scheme_metas=[meta], host_metas=[_HOST_META], suite_xml=_SUITE_XML)
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    SchemeIOCapturePass(
        scheme="test_io_capture_scheme", phase=phase, test_driver_dir=str(tmp_path),
    ).apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    path = tmp_path / "test_test_io_capture_scheme.F90"
    return out.getvalue(), (path.read_text() if path.exists() else None)


def test_uncaptured_init_is_called_once_before_the_run_replay(run_host_match, ccpp_context, tmp_path):
    """An init with only errmsg/errflg has nothing captured, but the run
    phase may read module state it sets: the driver calls it once, first,
    with no capture file and no compare; errflg is still checked."""
    fortran, driver = _driver_with_init(run_host_match, ccpp_context, tmp_path, CCPP_MANDATORY_ARGS)
    assert "ccpp_capture_begin('test_io_capture_scheme_init'" not in fortran
    assert driver is not None
    init_call = driver.index("  call test_io_capture_scheme_init(")
    assert "! -- test_io_capture_scheme_init (nothing captured: called once, not compared) --" in driver
    assert 'ccpp_capture_open_call("test_io_capture_scheme_init"' not in driver
    assert init_call < driver.index('ccpp_capture_open_call("test_io_capture_scheme_run"')
    after_init = driver[init_call:driver.index("  ! -- test_io_capture_scheme_run --")]
    assert "if (errflg /= 0) then" in after_init
    assert "n_failed = n_failed + 1" in after_init
    assert "use test_io_capture_scheme, only: test_io_capture_scheme_init" in driver


def _run_with_other_kind_init(run_host_match, ccpp_context, tmp_path):
    """Generate with an init whose only non-error argument is a real of
    another kind: nothing captured, and the driver cannot supply it."""
    other_kind = """[ other_var ]
  standard_name = test_capture_other_kind_var
  units = K
  type = real | kind = kind_other
  dimensions = ()
  intent = in
""" + CCPP_MANDATORY_ARGS
    host = _HOST_META + """[ other_var ]
  standard_name = test_capture_other_kind_var
  units = K
  type = real | kind = kind_other
  dimensions = ()
"""
    head, _init = _SCHEME_META.split(_INIT_TABLE_HEAD)
    module = run_host_match(scheme_metas=[head + _INIT_TABLE_HEAD + other_kind],
                            host_metas=[host], suite_xml=_SUITE_XML)
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    SchemeIOCapturePass(
        scheme="test_io_capture_scheme", test_driver_dir=str(tmp_path),
    ).apply(ccpp_context, module)


def test_uncaptured_phase_needing_other_arguments_is_left_out(run_host_match, ccpp_context, tmp_path):
    """An init with nothing captured but an argument the driver cannot
    supply (here a real of another kind) is still skipped."""
    _run_with_other_kind_init(run_host_match, ccpp_context, tmp_path)
    driver = (tmp_path / "test_test_io_capture_scheme.F90").read_text()
    assert "test_io_capture_scheme_init" not in driver
    assert 'ccpp_capture_open_call("test_io_capture_scheme_run"' in driver


def test_no_driver_with_only_a_call_only_phase(run_host_match, ccpp_context, tmp_path):
    """A driver needs a compared phase: capturing only an init with
    nothing to capture writes no driver."""
    _fortran, driver = _driver_with_init(run_host_match, ccpp_context, tmp_path,
                                         CCPP_MANDATORY_ARGS, phase="initialize")
    assert driver is None


# scheme-io-capture-skip-message: a phase left out of the driver is reported
# as a warning and in test_<scheme>.skipped next to the drivers.
_SKIP_FILE = "test_test_io_capture_scheme.skipped"


def test_skipped_phase_reported_with_its_reason(run_host_match, ccpp_context, tmp_path, capsys):
    from xdsl_ccpp.util import errors
    errors._WARNED.clear()
    _run_with_other_kind_init(run_host_match, ccpp_context, tmp_path)
    reason = ("nothing in it is captured, and the driver cannot supply argument "
              "'other_var' (real, kind kind_other)")
    err = capsys.readouterr().err
    assert ("Warning: scheme I/O capture: test_io_capture_scheme_init left out of "
            f"the test driver: {reason}") in err
    report = (tmp_path / _SKIP_FILE).read_text()
    assert f"test_io_capture_scheme_init: {reason}\n" in report
    assert "test_io_capture_scheme_run" not in report  # it has a driver


def test_stale_skip_report_removed_when_nothing_is_skipped(run_host_match, ccpp_context, tmp_path):
    (tmp_path / _SKIP_FILE).write_text("stale\n")
    _driver_with_init(run_host_match, ccpp_context, tmp_path, CCPP_MANDATORY_ARGS)
    assert (tmp_path / "test_test_io_capture_scheme.F90").exists()
    assert not (tmp_path / _SKIP_FILE).exists()


def test_no_driver_reported_when_no_phase_is_compared(run_host_match, ccpp_context, tmp_path):
    """Only a call-only phase captured: no driver, and the report says why."""
    _driver_with_init(run_host_match, ccpp_context, tmp_path,
                      CCPP_MANDATORY_ARGS, phase="initialize")
    report = (tmp_path / _SKIP_FILE).read_text()
    assert ("test_io_capture_scheme: no test_test_io_capture_scheme.F90 written: its "
            "phases have nothing captured, so there is nothing to compare") in report


def test_unresolved_dimension_named_in_the_reason():
    """The reason names the uncaptured array and its missing dimension."""
    from xdsl_ccpp.transforms.scheme_io_capture_pass import _unresolved_dims_reason

    class _Arg:
        _attrs = {"type": "real", "kind": "pumas_r8", "dimensions": 2,
                  "dim_names": ["horizontal_loop_extent", "microphysics_vertical_layer_dimension"]}

        def hasAttr(self, name):
            return name in self._attrs

        def getAttr(self, name):
            return self._attrs[name]

    reason = _unresolved_dims_reason("pumas_x", _Arg(), {"horizontal_loop_extent": "ncol"})
    assert reason == (
        "argument 'pumas_x' (real, kind pumas_r8, rank 2) is outside the capture's type "
        "scope, so the driver must size it from the other arguments, but its dimension "
        "'microphysics_vertical_layer_dimension' is not an argument of the call"
    )


# scheme-io-capture-real-kinds: reals of a kind equal to kind_phys (a
# metadata kind_spec kind such as PUMAS's pumas_r8, or an iso_fortran_env
# alias with kind_phys's value) are captured and compared.

def test_phys_real_kinds_rule():
    from xdsl.dialects import builtin
    from xdsl_ccpp.dialects import ccpp
    from xdsl_ccpp.transforms.scheme_io_capture_pass import _phys_real_kinds

    kinds = ccpp.KindsOp([
        ccpp.KindOp("kind_phys", "REAL64"),
        ccpp.KindOp("r8", "REAL64"),
        ccpp.KindOp("r4", "REAL32"),
        ccpp.KindOp("pumas_r8", "kind_r8", "pumas_kinds"),
    ])
    mod = builtin.ModuleOp([kinds], sym_name=builtin.StringAttr("ccpp"))
    assert _phys_real_kinds(mod) == frozenset({"kind_phys", "r8", "pumas_r8"})
    assert _phys_real_kinds(None) == frozenset({"kind_phys"})


def test_capture_scope_takes_the_equal_kinds():
    kinds = frozenset({"kind_phys", "pumas_r8"})
    assert _is_capture_supported("real", "pumas_r8", 2, kinds)
    assert not _is_capture_supported("real", "pumas_r8", 2)
    assert not _is_capture_supported("real", "r4", 2, kinds)


def test_kind_spec_real_captured_and_compared(run_host_match, ccpp_context, tmp_path):
    """A real of a kind_spec kind is captured in the cap and compared in the
    driver, which imports the kind from ccpp_kinds."""
    meta = _SCHEME_META.replace(
        "  name = test_io_capture_scheme\n  type = scheme\n",
        "  name = test_io_capture_scheme\n  type = scheme\n"
        "  kind_spec = my_kinds:my_r8=>kind_r8\n", 1,
    ).replace(
        "[ in_var ]\n  standard_name = test_capture_in_var\n  units = K\n"
        "  type = real | kind = kind_phys",
        "[ in_var ]\n  standard_name = test_capture_in_var\n  units = K\n"
        "  type = real | kind = my_r8",
    )
    host = _HOST_META.replace(
        "[ in_var ]\n  standard_name = test_capture_in_var\n  units = K\n"
        "  type = real | kind = kind_phys",
        "[ in_var ]\n  standard_name = test_capture_in_var\n  units = K\n"
        "  type = real | kind = my_r8",
    )
    assert meta.count("kind = my_r8") == 2 and host.count("kind = my_r8") == 1
    module = run_host_match(scheme_metas=[meta], host_metas=[host], suite_xml=_SUITE_XML)
    from xdsl_ccpp.transforms.suite_kinds import MetaKind
    MetaKind().apply(ccpp_context, module)
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    SchemeIOCapturePass(
        scheme="test_io_capture_scheme", test_driver_dir=str(tmp_path),
    ).apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    assert "'in_var', in_var" in _block(out.getvalue(), _BEGIN_BEFORE)
    driver = (tmp_path / "test_test_io_capture_scheme.F90").read_text()
    assert "  use ccpp_kinds, only: kind_phys, my_r8\n" in driver
    assert "real(kind=my_r8) :: in_var" in driver
    assert 'ccpp_capture_read("in", "in_var", in_var)' in driver
