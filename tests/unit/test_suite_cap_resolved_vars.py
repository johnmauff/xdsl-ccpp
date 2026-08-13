"""Unit tests for SuiteCAP's --emit-resolved-vars JSON output
(capgen_v1_parity_backlog.md Stage 3/4).

Covers the fix for the Stage 4 gap: _classify_args's physics-mode dispatch
replaces a scheme-declared horizontal_loop_extent arg with synthetic,
nameless col_start/col_end scalars, which used to silently drop the
loop-extent variable's standard_name identity from the resolved-vars output
entirely (_resolved_var_record correctly filters out args with no
standard_name, but that filter was also eating the *original* loop-extent
arg, not just the col_start/col_end synthetics). Fixed by folding
_classify_args's ncol_meta (the original, unreplaced arg) back into the
stash, and normalizing deprecated standard names (horizontal_loop_extent ->
horizontal_dimension) via CCPP_DEPRECATED_STD_NAMES so the output matches
capgen-v1's own naming convention.
"""

import json

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

import pytest

pytestmark = pytest.mark.usefixtures("legacy_mode")

_CHUNKED_SCHEME_META = f"""\
[ccpp-table-properties]
  name = chunked_scheme
  type = scheme
[ccpp-arg-table]
  name = chunked_scheme_run
  type = scheme
[ ncol ]
  standard_name = horizontal_loop_extent
  units = count
  type = integer
  dimensions = ()
  intent = in
[ x ]
  standard_name = some_array_var
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_loop_extent)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""


def _run_phase_records(run_host_match, ccpp_context, tmp_path) -> list[dict]:
    module = run_host_match(
        scheme_metas=[_CHUNKED_SCHEME_META],
        host_metas=[],
        suite_xml=minimal_suite_xml("chunked_scheme"),
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    out_path = tmp_path / "resolved_vars.json"
    SuiteCAP(emit_resolved_vars=str(out_path)).apply(ccpp_context, module)
    with open(out_path) as f:
        data = json.load(f)
    return data["phases"]["run"]


def test_loop_extent_identity_survives_col_start_col_end_synthesis(
    run_host_match, ccpp_context, tmp_path
):
    """The scheme's own horizontal_loop_extent scalar is replaced by
    synthetic col_start/col_end in the suite callee's arg list, but its
    standard-name identity (recovered via _classify_args's ncol_meta) must
    still appear in the run-phase resolved-vars record -- this is the
    variable write_init_files.py-style consumers need to resolve a
    horizontal-dimension binding for, and it must not be silently dropped
    just because the synthetic col_start/col_end scalars correctly are."""
    records = _run_phase_records(run_host_match, ccpp_context, tmp_path)
    names = [r["standard_name"] for r in records]
    assert "horizontal_dimension" in names, names
    assert "horizontal_loop_extent" not in names, (
        "deprecated standard name leaked through unnormalized"
    )


def test_dim_names_normalized_to_modern_standard_name(
    run_host_match, ccpp_context, tmp_path
):
    """x is dimensioned by (horizontal_loop_extent) in the source .meta --
    its own resolved-var record's dim_names must report the modern
    horizontal_dimension name too, not just its own standard_name."""
    records = _run_phase_records(run_host_match, ccpp_context, tmp_path)
    x_record = next(r for r in records if r["standard_name"] == "some_array_var")
    assert x_record["dim_names"] == ["horizontal_dimension"], x_record["dim_names"]


def test_synthetic_col_start_col_end_scalars_still_excluded(
    run_host_match, ccpp_context, tmp_path
):
    """col_start/col_end themselves are nameless synthetic scalars with no
    CCPP metadata identity -- _resolved_var_record must keep dropping them,
    same as before this fix; only the original loop-extent arg's identity
    (folded back in via ncol_meta) should newly appear."""
    records = _run_phase_records(run_host_match, ccpp_context, tmp_path)
    names = [r["standard_name"] for r in records]
    assert "horizontal_dimension" in names
    assert names.count("horizontal_dimension") == 1, (
        "expected exactly one horizontal_dimension record, not a duplicate "
        f"per col_start/col_end synthetic: {names!r}"
    )
