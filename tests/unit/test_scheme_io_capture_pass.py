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
    assert fortran.count("call ccpp_capture_end()") == 4  # init + run, before + after
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
    assert fortran.count(set_dir) == 2  # init + run, "before" only
    assert fortran.count(f"'{tmp_path}')") == 2
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
    assert fortran.count(f"'{tmp_path / 'case.c01b'}')") == 2
    assert fortran.count("call ccpp_capture_set_info('case.c01b', 'xdsl_ccpp") == 2
    # The drivers stay in the driver directory itself.
    assert (tmp_path / "test_test_io_capture_scheme.F90").exists()


def test_set_info_records_generator_in_each_before_block(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    set_info = "call ccpp_capture_set_info('', 'xdsl_ccpp"
    assert fortran.count(set_info) == 2  # init + run
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
    assert "tolerance = ccpp_capture_tolerance_override(1.0e-10_kind_phys)" in driver_source


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
