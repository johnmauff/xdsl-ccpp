"""Unit tests for suite_cap.py's _apply_ddt_chain -- the --emit-resolved-vars
DDT-member chain resolution this PR (ddt-chain) introduces.

Confirmed missing before this file existed (flagged by Copilot review on
PR #54): no test covered the emitted JSON schema/values for a DDT-member
case at all, for either shape _apply_ddt_chain has to handle:

  1. The DDT instance lives in a MODULE-type table -- the common case
     (e.g. var_compat's own phys_state%scheme_order) -- model_module_name/
     import_name/call_expr should resolve to the real Fortran chain, and
     is_host_table_var must NOT be set.

  2. The DDT instance lives in a HOST-type table (e.g. ddthost's own
     ccpp_info_t, passed through the host's caller-provided argument list,
     not use-associated). Also flagged by Copilot review: _build_ddt_
     resolution_maps() deliberately scans both MODULE and HOST tables (a
     DDT instance can genuinely live in either), but a HOST-type table's
     contents are never `use`-associable -- run_dispatch.py's own real cap
     generation already checks this after resolving a DDT chain (see that
     file's own ArgSourceKind.Block branch); _apply_ddt_chain needed the
     same check, or --emit-resolved-vars would incorrectly suggest
     `use <host_table>, only: <instance_var>` is valid Fortran for case 2.
     Fixed by cap_shared.py's new _host_table_names() helper, threaded
     through ddt_resolution_maps into _apply_ddt_chain, which now sets
     is_host_table_var (the same flag host_var_match_pass.py already uses
     for a plain, non-DDT host-table match) whenever the resolved DDT
     instance itself lives in a HOST-type table.
"""

import json

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

# ── Scenario 1: DDT instance in a MODULE table (the common case) ──────────

_MODULE_HOST_META = """\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
[ phys_state ]
  standard_name = physics_state_derived_type
  long_name = Physics State DDT
  type = phys_state_t
  units = DDT
  dimensions = ()
"""

_MODULE_DDT_META = """\
[ccpp-table-properties]
  name = phys_state_t
  type = ddt
[ccpp-arg-table]
  name = phys_state_t
  type = ddt
[ counter ]
  standard_name = call_order_counter
  units = count
  type = integer
  dimensions = ()
"""

_MODULE_SCHEME_META = f"""\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
[ccpp-arg-table]
  name = scheme_a_run
  type = scheme
[ counter ]
  standard_name = call_order_counter
  units = count
  type = integer
  dimensions = ()
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

# ── Scenario 2: DDT instance in a HOST table (ddthost's own ccpp_info_t shape) ──

_HOST_TABLE_META = """\
[ccpp-table-properties]
  name = test_host
  type = host
[ccpp-arg-table]
  name = test_host
  type = host
[ ccpp_data ]
  standard_name = ccpp_handle_instance
  long_name = CCPP handle DDT instance
  type = ccpp_info_t
  units = DDT
  dimensions = ()
"""

_HOST_DDT_META = """\
[ccpp-table-properties]
  name = ccpp_info_t
  type = ddt
[ccpp-arg-table]
  name = ccpp_info_t
  type = ddt
[ col_start ]
  standard_name = horizontal_loop_begin
  units = count
  type = integer
  dimensions = ()
"""

_HOST_SCHEME_META = f"""\
[ccpp-table-properties]
  name = scheme_b
  type = scheme
[ccpp-arg-table]
  name = scheme_b_run
  type = scheme
[ col_start ]
  standard_name = horizontal_loop_begin
  units = count
  type = integer
  dimensions = ()
  intent = in
{CCPP_MANDATORY_ARGS}
"""


def _run_phase_records(run_host_match, ccpp_context, tmp_path, scheme_meta, host_metas, scheme_name) -> list[dict]:
    module = run_host_match(
        scheme_metas=[scheme_meta],
        host_metas=host_metas,
        suite_xml=minimal_suite_xml(scheme_name),
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    out_path = tmp_path / "resolved_vars.json"
    SuiteCAP(emit_resolved_vars=str(out_path)).apply(ccpp_context, module)
    with open(out_path) as f:
        data = json.load(f)
    return data["phases"]["run"]


class TestDdtChainModuleTableInstance:
    """DDT instance lives in a MODULE table -- the common, use-associable case."""

    def _record(self, run_host_match, ccpp_context, tmp_path) -> dict:
        records = _run_phase_records(
            run_host_match, ccpp_context, tmp_path,
            scheme_meta=_MODULE_SCHEME_META,
            host_metas=[_MODULE_HOST_META, _MODULE_DDT_META],
            scheme_name="scheme_a",
        )
        return next(r for r in records if r["standard_name"] == "call_order_counter")

    def test_resolves_to_real_module_and_instance(self, run_host_match, ccpp_context, tmp_path):
        record = self._record(run_host_match, ccpp_context, tmp_path)
        assert record["model_module_name"] == "test_host_mod", record
        assert record["import_name"] == "phys_state", record

    def test_call_expr_is_the_dotted_member_access(self, run_host_match, ccpp_context, tmp_path):
        record = self._record(run_host_match, ccpp_context, tmp_path)
        assert record["call_expr"] == "phys_state%counter", record

    def test_not_flagged_as_host_table_var(self, run_host_match, ccpp_context, tmp_path):
        """A MODULE-table instance is genuinely `use`-associable -- must not
        be flagged the same way a HOST-table instance is."""
        record = self._record(run_host_match, ccpp_context, tmp_path)
        assert not record.get("is_host_table_var"), record


class TestDdtChainHostTableInstance:
    """DDT instance lives in a HOST table (ddthost's own ccpp_info_t shape)
    -- the case this PR's own review comment flagged as unhandled."""

    def _record(self, run_host_match, ccpp_context, tmp_path) -> dict:
        records = _run_phase_records(
            run_host_match, ccpp_context, tmp_path,
            scheme_meta=_HOST_SCHEME_META,
            host_metas=[_HOST_TABLE_META, _HOST_DDT_META],
            scheme_name="scheme_b",
        )
        return next(r for r in records if r["standard_name"] == "horizontal_loop_begin")

    def test_flagged_as_host_table_var(self, run_host_match, ccpp_context, tmp_path):
        """The actual regression this fix closes: a DDT instance living in
        a HOST-type table must be flagged is_host_table_var, exactly like
        host_var_match_pass.py's own plain (non-DDT) host-table match
        already is -- a consumer checking that flag (as it must for the
        plain case) will then correctly treat this as a caller-provided
        block argument rather than something `use <test_host>, only:
        ccpp_data` could validly import."""
        record = self._record(run_host_match, ccpp_context, tmp_path)
        assert record.get("is_host_table_var") is True, record

    def test_call_expr_still_correctly_resolved(self, run_host_match, ccpp_context, tmp_path):
        """Being caller-provided rather than use-associable doesn't make
        the dotted access path itself wrong -- ccpp_data%col_start is still
        the real Fortran expression a consumer needs."""
        record = self._record(run_host_match, ccpp_context, tmp_path)
        assert record["call_expr"] == "ccpp_data%col_start", record
