"""Unit tests for metadata ``kind_spec`` support.

Real capgen-v1 lets a ``.meta`` table's ``[ccpp-table-properties]`` block
declare ``kind_spec = <module>:<kind_name>=>spec`` (or the ``<module>:<spec>``
shorthand) to say a kind comes from a real host/scheme Fortran module instead
of the hardcoded ISO_FORTRAN_ENV table -- see ccpp_cap_refactor_plan.md's
"kind_spec" backlog entry and capgen-v1's own
metadata/metadata_table.py:_parse_kind_spec_value / ccpp_capgen.py's
_collect_metadata_kind_specs, which this mirrors.
"""

import pytest
from xdsl.dialects.builtin import ModuleOp
from xdsl.utils.hints import isa

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.frontend.ccpp_xml import _parse_kind_spec_value
from xdsl_ccpp.transforms.suite_kinds import MetaKind
from xdsl_ccpp.transforms.suite_meta import MetaCAP


class TestParseKindSpecValue:
    def test_explicit_kind_name(self):
        assert _parse_kind_spec_value("temp_kinds:kind_temp=>temp_r8") == (
            "kind_temp", "temp_kinds", "temp_r8",
        )

    def test_shorthand_kind_name_defaults_to_spec(self):
        assert _parse_kind_spec_value("host_kinds:kind_r8") == (
            "kind_r8", "host_kinds", "kind_r8",
        )

    def test_tolerates_surrounding_whitespace(self):
        assert _parse_kind_spec_value("  temp_kinds : kind_temp => temp_r8  ") == (
            "kind_temp", "temp_kinds", "temp_r8",
        )

    def test_malformed_value_raises(self):
        with pytest.raises(ValueError, match="Malformed kind_spec"):
            _parse_kind_spec_value("not_a_kind_spec")


def _scheme_with_kind_spec(name: str, kind_spec: str, kind_name: str) -> str:
    return f"""\
[ccpp-table-properties]
  name = {name}
  type = scheme
  kind_spec = {kind_spec}
[ccpp-arg-table]
  name = {name}_run
  type = scheme
[ x ]
  standard_name = test_kind_var_{name}
  units = 1
  type = real
  kind = {kind_name}
  dimensions = ()
  intent = in
{CCPP_MANDATORY_ARGS}
"""


def _resolved_kinds(ccpp_context, module) -> dict[str, tuple[str, str]]:
    """Run MetaCAP + MetaKind and return kind_name -> (value, module)."""
    MetaCAP().apply(ccpp_context, module)
    MetaKind().apply(ccpp_context, module)

    ccpp_module = next(
        op for op in module.body.ops
        if isa(op, ModuleOp) and op.sym_name is not None and op.sym_name.data == "ccpp"
    )
    for inner_op in ccpp_module.body.ops:
        if isa(inner_op, ccpp.KindsOp):
            return {
                kind_op.kind_name.data: (kind_op.kind_value.data, kind_op.kind_module.data)
                for kind_op in inner_op.body.ops
                if isa(kind_op, ccpp.KindOp)
            }
    return {}


class TestMetaKindSpecResolution:
    def test_kind_spec_resolves_to_declared_module(self, build_module, ccpp_context):
        module = build_module(
            [_scheme_with_kind_spec("scheme_a", "temp_kinds:kind_temp=>temp_r8", "kind_temp")],
            [], None,
        )
        assert _resolved_kinds(ccpp_context, module) == {"kind_temp": ("temp_r8", "temp_kinds")}

    def test_kind_without_kind_spec_still_falls_back_to_iso(self, build_module, ccpp_context):
        """kind_phys with no kind_spec declaration keeps today's implicit
        ISO_FORTRAN_ENV resolution -- adding kind_spec support must not change
        this for every example that never declares one."""
        module = build_module(
            [_scheme_with_kind_spec("scheme_a", "temp_kinds:kind_temp=>temp_r8", "kind_phys")],
            [], None,
        )
        resolved = _resolved_kinds(ccpp_context, module)
        assert resolved["kind_phys"] == ("REAL64", "iso_fortran_env")

    def test_agreeing_kind_spec_declarations_across_tables_is_fine(self, build_module, ccpp_context):
        module = build_module(
            [
                _scheme_with_kind_spec("scheme_a", "temp_kinds:kind_temp=>temp_r8", "kind_temp"),
                _scheme_with_kind_spec("scheme_b", "temp_kinds:kind_temp=>temp_r8", "kind_temp"),
            ],
            [], None,
        )
        assert _resolved_kinds(ccpp_context, module) == {"kind_temp": ("temp_r8", "temp_kinds")}

    def test_conflicting_kind_spec_declarations_raise(self, build_module, ccpp_context):
        module = build_module(
            [
                _scheme_with_kind_spec("scheme_a", "temp_kinds:kind_temp=>temp_r8", "kind_temp"),
                _scheme_with_kind_spec("scheme_b", "other_kinds:kind_temp=>other_r8", "kind_temp"),
            ],
            [], None,
        )
        with pytest.raises(ValueError, match="Conflicting kind_spec"):
            _resolved_kinds(ccpp_context, module)
