"""Unit tests for `--capture-scheme` (SchemeIOCapturePass).

scheme-io-capture (BACKLOG.md). PR 1 scope: the pass itself, unit-tested
only -- the real ccpp_capture_mod.F90 runtime library doesn't exist yet
(a later PR), so these tests assert on the generated call *text* and
*position*, not a real compile. Same harness/style as
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
from xdsl_ccpp.transforms.scheme_io_capture_pass import SchemeIOCapturePass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

pytestmark = pytest.mark.usefixtures("legacy_mode")

# Covers every v1-relevant shape in one scheme, two entry points:
#  - in_var:    intent=in, real(kind_phys)   -> one capture, before only.
#  - out_var:   intent=out, integer          -> one capture, after only.
#  - io_var:    intent=inout, real(kind_phys), device-resident, rank 2
#               -> two captures (before + after), each preceded by a sync.
#  - skip_opt:  intent=in, optional          -> never captured.
#  - skip_str:  type=character (not in {integer,logical,real(kind_phys)})
#               -> never captured (also covers errmsg's own type, just
#               confirmed via a second, non-mandatory argument).
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


def _fortran_output(run_host_match, ccpp_context, scheme="", phase="", directive=None) -> str:
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
    SchemeIOCapturePass(scheme=scheme, phase=phase, directive=directive).apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def test_no_effect_when_scheme_unset(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="")
    assert "ccpp_capture_" not in fortran


def test_no_effect_for_unmatched_scheme_name(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="nonexistent_scheme")
    assert "ccpp_capture_" not in fortran


def test_intent_in_scalar_captured_before_only(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    call = 'call test_io_capture_scheme_run('
    before_tag = '"test_io_capture_scheme_run:in_var:in:before"'
    assert before_tag in fortran
    # Exactly one capture for an in-only scalar -- no :after tag at all.
    assert 'in_var:in:after' not in fortran
    assert f'call ccpp_capture_r8_0d({before_tag}, in_var)' in fortran
    # Positioned before the real call, not after.
    assert fortran.index(before_tag) < fortran.index(call)


def test_intent_out_scalar_captured_after_only(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    call = 'call test_io_capture_scheme_run('
    after_tag = '"test_io_capture_scheme_run:out_var:out:after"'
    assert after_tag in fortran
    assert 'out_var:out:before' not in fortran
    assert f'call ccpp_capture_int_0d({after_tag}, out_var)' in fortran
    assert fortran.index(call) < fortran.index(after_tag)


def test_intent_inout_array_captured_both_with_device_sync(run_host_match, ccpp_context):
    fortran = _fortran_output(
        run_host_match, ccpp_context, scheme="test_io_capture_scheme", directive="acc",
    )
    before_tag = '"test_io_capture_scheme_run:io_var:inout:before"'
    after_tag = '"test_io_capture_scheme_run:io_var:inout:after"'
    assert f'call ccpp_capture_r8_2d({before_tag}, io_var)' in fortran
    assert f'call ccpp_capture_r8_2d({after_tag}, io_var)' in fortran
    # A device-resident arg must get an update-self sync immediately
    # before each capture read.
    assert fortran.count("update self(io_var)") == 2
    # Ordering: sync-then-capture before the call, call-then-sync-then-
    # capture after it.
    call_pos = fortran.index("call test_io_capture_scheme_run(")
    before_sync_pos = fortran.rindex("update self(io_var)", 0, call_pos)
    before_capture_pos = fortran.index(before_tag)
    assert before_sync_pos < before_capture_pos < call_pos
    after_capture_pos = fortran.index(after_tag)
    after_sync_pos = fortran.rindex("update self(io_var)", call_pos, after_capture_pos)
    assert call_pos < after_sync_pos < after_capture_pos


def test_no_device_sync_without_directive(run_host_match, ccpp_context):
    # Same io_var, but no --directive at all -- there's no GPU residency
    # to sync, so no update self(...) should appear even though io_var is
    # declared memory_space=device.
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    assert "update self(io_var)" not in fortran
    assert '"test_io_capture_scheme_run:io_var:inout:before"' in fortran


def test_optional_argument_never_captured(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    # Tags are the only place a captured arg's own name appears in
    # generated code (quoted string literals, odd-indexed splits on `"`)
    # -- skip_opt must never appear in one.
    for tag_fragment in fortran.split('"')[1::2]:
        assert "skip_opt" not in tag_fragment


def test_unsupported_type_never_captured(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    for tag_fragment in fortran.split('"')[1::2]:
        assert "skip_str" not in tag_fragment


def test_errmsg_errflg_never_captured(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    for tag_fragment in fortran.split('"')[1::2]:
        assert "errmsg" not in tag_fragment
        assert "errflg" not in tag_fragment


def test_phase_filter_restricts_to_one_entry_point(run_host_match, ccpp_context):
    # The scheme's own callee subroutines (test_io_capture_scheme_run/
    # _init) are never printed in generated output -- only the suite-level
    # wrapper that calls them is -- so check by tag content (each tag
    # embeds its own table_name) rather than slicing a subroutine body
    # that doesn't exist in this text at all.
    fortran = _fortran_output(
        run_host_match, ccpp_context, scheme="test_io_capture_scheme", phase="run",
    )
    assert "test_io_capture_scheme_run:in_var" in fortran
    assert "test_io_capture_scheme_init:in_var" not in fortran


def test_no_phase_filter_captures_every_entry_point(run_host_match, ccpp_context):
    fortran = _fortran_output(run_host_match, ccpp_context, scheme="test_io_capture_scheme")
    assert "test_io_capture_scheme_run:in_var" in fortran
    assert "test_io_capture_scheme_init:in_var" in fortran
