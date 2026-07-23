"""Unit tests for xdsl_ccpp.transforms.suite_kinds.MetaKind.

A numeric kind literal (e.g. ``kind = 8``) is already valid, self-contained
Fortran (``real(kind=8)``) with no ``ccpp_kinds`` dependency -- unlike a
named kind (``kind_phys``), it must not be collected as a symbolic name to
declare/export, or ``generate-kinds`` emits an invalid ``public :: 8``.
Found via a Copilot review comment on examples/var_compat's real generated
``ccpp_kinds.F90`` (PR #41) -- ``effr_calc.meta``'s real ``effrs_inout`` arg
genuinely uses ``kind = 8``.
"""

from xdsl.dialects.builtin import ModuleOp
from xdsl.utils.hints import isa

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.transforms.suite_kinds import MetaKind
from xdsl_ccpp.transforms.suite_meta import MetaCAP


def _scheme_with_real_arg(name: str, kind: str) -> str:
    return f"""\
[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_run
  type = scheme
[ x ]
  standard_name = test_kind_var_{name}
  units = 1
  type = real
  kind = {kind}
  dimensions = ()
  intent = in
{CCPP_MANDATORY_ARGS}
"""


def _collected_kind_names(ccpp_context, module) -> list[str]:
    MetaCAP().apply(ccpp_context, module)
    MetaKind().apply(ccpp_context, module)

    ccpp_module = next(
        op for op in module.body.ops
        if isa(op, ModuleOp) and op.sym_name is not None and op.sym_name.data == "ccpp"
    )
    for inner_op in ccpp_module.body.ops:
        if isa(inner_op, ccpp.KindsOp):
            return [
                kind_op.kind_name.data
                for kind_op in inner_op.body.ops
                if isa(kind_op, ccpp.KindOp)
            ]
    return []


class TestMetaKindNumericLiteral:
    def test_numeric_kind_literal_is_not_collected(self, build_module, ccpp_context):
        module = build_module([_scheme_with_real_arg("scheme_a", "8")], [], None)
        assert _collected_kind_names(ccpp_context, module) == []

    def test_named_kind_is_still_collected(self, build_module, ccpp_context):
        module = build_module([_scheme_with_real_arg("scheme_a", "kind_phys")], [], None)
        assert _collected_kind_names(ccpp_context, module) == ["kind_phys"]

    def test_named_kind_and_numeric_literal_together(self, build_module, ccpp_context):
        """The exact examples/var_compat shape: one scheme's real arg uses a
        named kind, another's uses a bare numeric literal -- only the named
        one should be collected."""
        module = build_module(
            [
                _scheme_with_real_arg("scheme_a", "kind_phys"),
                _scheme_with_real_arg("scheme_b", "8"),
            ],
            [],
            None,
        )
        assert _collected_kind_names(ccpp_context, module) == ["kind_phys"]
