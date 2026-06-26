"""Unit tests for HostVariableMatchPass.

Mirrors the role of ccpp-capgen's test/unit_tests/test_var_transforms.py —
testing variable matching and compatibility logic in isolation without any
Fortran compilation.

Each test supplies minimal .meta content as strings, runs the pass, and
asserts on the outcome (error raised, warning emitted, or IR annotation set).
"""

import pytest

from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp import ArgumentOp, TablePropertiesOp, TableTypeKind
from xdsl.dialects.builtin import ModuleOp

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml


# ── Meta content helpers ──────────────────────────────────────────────────────

def scheme_meta(name: str, extra_run_args: str = "") -> str:
    """Minimal scheme .meta with one configurable run argument."""
    return f"""\
[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_run
  type = scheme
{extra_run_args}
{CCPP_MANDATORY_ARGS}
"""


def host_meta(name: str, vars_content: str) -> str:
    """Minimal host module .meta."""
    return f"""\
[ccpp-table-properties]
  name = {name}
  type = module
[ccpp-arg-table]
  name = {name}
  type = module
{vars_content}
"""


# Reusable single-variable snippets (scheme side)
SCHEME_REAL_VAR = """\
[ var_a ]
  standard_name = some_variable
  type = real
  kind = kind_phys
  intent = inout
  dimensions = (horizontal_dimension)
  units = K
"""

SCHEME_REAL_2D_VAR = """\
[ var_a ]
  standard_name = some_variable
  type = real
  kind = kind_phys
  intent = inout
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  units = K
"""

SCHEME_REAL_VAR_IN = """\
[ var_a ]
  standard_name = some_variable
  type = real
  kind = kind_phys
  intent = in
  dimensions = ()
  units = K
"""

SCHEME_REAL_VAR_OUT = """\
[ var_a ]
  standard_name = some_variable
  type = real
  kind = kind_phys
  intent = out
  dimensions = ()
  units = K
"""

SCHEME_OPTIONAL_VAR = """\
[ var_opt ]
  standard_name = optional_variable
  type = real
  kind = kind_phys
  intent = inout
  dimensions = ()
  units = K
  optional = .true.
"""

# Reusable single-variable snippets (host side)
HOST_REAL_VAR = """\
[ host_var_a ]
  standard_name = some_variable
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  units = K
"""

HOST_INTEGER_VAR = """\
[ host_var_a ]
  standard_name = some_variable
  type = integer
  dimensions = ()
  units = count
"""

HOST_REAL_1D_VAR = """\
[ host_var_a ]
  standard_name = some_variable
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  units = K
"""

HOST_REAL_KIND_DYN = """\
[ host_var_a ]
  standard_name = some_variable
  type = real
  kind = kind_dyn
  dimensions = (horizontal_dimension)
  units = K
"""

HOST_REAL_INTENT_IN = """\
[ host_var_a ]
  standard_name = some_variable
  type = real
  kind = kind_phys
  intent = in
  dimensions = ()
  units = K
"""

HOST_REAL_INTENT_OUT = """\
[ host_var_a ]
  standard_name = some_variable
  type = real
  kind = kind_phys
  intent = out
  dimensions = ()
  units = K
"""


# ── Helper: find a ccpp.arg op by standard name in the matched @ccpp module ──

def _get_scheme_arg(module: ModuleOp, scheme_name: str, arg_std_name: str):
    """Return the first scheme ccpp.ArgumentOp with the given standard_name."""
    from xdsl.dialects.builtin import ModuleOp as BuiltinModuleOp
    for op in module.body.block.ops:
        if not (isa(op, BuiltinModuleOp) and op.sym_name
                and op.sym_name.data == "ccpp"):
            continue
        for tpop in op.body.ops:
            if not isa(tpop, TablePropertiesOp):
                continue
            if tpop.table_type.data != TableTypeKind.Scheme:
                continue
            if tpop.table_name.data != scheme_name:
                continue
            for atop in tpop.body.ops:
                for aop in atop.body.ops:
                    if not isa(aop, ArgumentOp):
                        continue
                    if (aop.standard_name is not None
                            and aop.standard_name.data == arg_std_name):
                        return aop
    return None


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestSuccessfulMatch:

    def test_compatible_real_vars(self, run_host_match):
        """Matching real variables with same kind and compatible intent succeed."""
        module = run_host_match(
            scheme_metas=[scheme_meta("test_scheme", SCHEME_REAL_VAR)],
            host_metas=[host_meta("test_mod", HOST_REAL_VAR)],
        )
        arg = _get_scheme_arg(module, "test_scheme", "some_variable")
        assert arg is not None
        assert arg.model_var_name is not None
        assert arg.model_var_name.data == "host_var_a"
        assert arg.model_module_name.data == "test_mod"

    def test_valid_dim_substitution(self, run_host_match):
        """horizontal_loop_extent (scheme) → horizontal_dimension (host) is valid."""
        scheme = scheme_meta("test_scheme", """\
[ var_a ]
  standard_name = some_variable
  type = real
  kind = kind_phys
  intent = inout
  dimensions = (horizontal_loop_extent)
  units = K
""")
        host = host_meta("test_mod", """\
[ host_var_a ]
  standard_name = some_variable
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  units = K
""")
        # Should not raise
        run_host_match(
            scheme_metas=[scheme],
            host_metas=[host],
        )

    def test_optional_var_with_no_match(self, run_host_match):
        """An optional argument with no host match does not raise."""
        run_host_match(
            scheme_metas=[scheme_meta("test_scheme", SCHEME_OPTIONAL_VAR)],
            host_metas=[host_meta("test_mod", HOST_REAL_VAR)],
        )


class TestTypeMismatch:

    def test_real_vs_integer_raises(self, run_host_match):
        """Scheme expects real but host provides integer → hard error."""
        with pytest.raises(ValueError, match="type mismatch"):
            run_host_match(
                scheme_metas=[scheme_meta("test_scheme", SCHEME_REAL_VAR)],
                host_metas=[host_meta("test_mod", HOST_INTEGER_VAR)],
            )

    def test_error_names_both_types(self, run_host_match):
        """Error message includes both scheme and host type names."""
        with pytest.raises(ValueError, match="real") as exc_info:
            run_host_match(
                scheme_metas=[scheme_meta("test_scheme", SCHEME_REAL_VAR)],
                host_metas=[host_meta("test_mod", HOST_INTEGER_VAR)],
            )
        assert "integer" in str(exc_info.value)


class TestDimensionMismatch:

    def test_rank_mismatch_raises(self, run_host_match):
        """Scheme has 2 dims but host has 1 → hard error."""
        with pytest.raises(ValueError, match="dimension rank mismatch"):
            run_host_match(
                scheme_metas=[scheme_meta("test_scheme", SCHEME_REAL_2D_VAR)],
                host_metas=[host_meta("test_mod", HOST_REAL_1D_VAR)],
            )

    def test_error_reports_both_ranks(self, run_host_match):
        """Rank mismatch error reports scheme and host dimension counts."""
        with pytest.raises(ValueError) as exc_info:
            run_host_match(
                scheme_metas=[scheme_meta("test_scheme", SCHEME_REAL_2D_VAR)],
                host_metas=[host_meta("test_mod", HOST_REAL_1D_VAR)],
            )
        msg = str(exc_info.value)
        assert "2" in msg
        assert "1" in msg


class TestIntentMismatch:

    def test_host_in_scheme_inout_raises(self, run_host_match):
        """Host read-only + scheme inout → scheme can't write → error."""
        with pytest.raises(ValueError, match="intent mismatch"):
            run_host_match(
                scheme_metas=[scheme_meta("test_scheme", SCHEME_REAL_VAR)],
                host_metas=[host_meta("test_mod", HOST_REAL_INTENT_IN)],
            )

    def test_host_out_scheme_inout_raises(self, run_host_match):
        """Host uninitialized before call + scheme reads it → error."""
        with pytest.raises(ValueError, match="intent mismatch"):
            run_host_match(
                scheme_metas=[scheme_meta("test_scheme", SCHEME_REAL_VAR)],
                host_metas=[host_meta("test_mod", HOST_REAL_INTENT_OUT)],
            )

    def test_host_in_scheme_out_raises(self, run_host_match):
        """Host read-only + scheme writes to it → error."""
        with pytest.raises(ValueError, match="intent mismatch"):
            run_host_match(
                scheme_metas=[scheme_meta("test_scheme", SCHEME_REAL_VAR_OUT)],
                host_metas=[host_meta("test_mod", HOST_REAL_INTENT_IN)],
            )

    def test_host_out_scheme_in_raises(self, run_host_match):
        """Host uninitialized + scheme reads it → error."""
        with pytest.raises(ValueError, match="intent mismatch"):
            run_host_match(
                scheme_metas=[scheme_meta("test_scheme", SCHEME_REAL_VAR_IN)],
                host_metas=[host_meta("test_mod", HOST_REAL_INTENT_OUT)],
            )

    def test_error_message_explains_access(self, run_host_match):
        """Intent error message explains read vs write access."""
        with pytest.raises(ValueError) as exc_info:
            run_host_match(
                scheme_metas=[scheme_meta("test_scheme", SCHEME_REAL_VAR)],
                host_metas=[host_meta("test_mod", HOST_REAL_INTENT_IN)],
            )
        msg = str(exc_info.value)
        assert "write" in msg or "read" in msg

    def test_no_intent_on_host_is_ok(self, run_host_match):
        """Module variables with no intent declaration are always accessible."""
        run_host_match(
            scheme_metas=[scheme_meta("test_scheme", SCHEME_REAL_VAR)],
            host_metas=[host_meta("test_mod", HOST_REAL_VAR)],
        )


class TestKindMismatch:

    def test_kind_mismatch_does_not_raise(self, run_host_match):
        """Kind mismatch is a warning, not a hard error — pipeline continues."""
        module = run_host_match(
            scheme_metas=[scheme_meta("test_scheme", SCHEME_REAL_VAR)],
            host_metas=[host_meta("test_mod", HOST_REAL_KIND_DYN)],
        )
        assert module is not None

    def test_kind_mismatch_warns_to_stderr(self, run_host_match, capsys):
        """Kind mismatch prints a warning to stderr."""
        run_host_match(
            scheme_metas=[scheme_meta("test_scheme", SCHEME_REAL_VAR)],
            host_metas=[host_meta("test_mod", HOST_REAL_KIND_DYN)],
        )
        captured = capsys.readouterr()
        assert "kind mismatch" in captured.err.lower()

    def test_kind_mismatch_annotates_arg_op(self, run_host_match):
        """Kind mismatch sets model_var_kind_mismatch on the scheme ccpp.arg op."""
        module = run_host_match(
            scheme_metas=[scheme_meta("test_scheme", SCHEME_REAL_VAR)],
            host_metas=[host_meta("test_mod", HOST_REAL_KIND_DYN)],
        )
        arg = _get_scheme_arg(module, "test_scheme", "some_variable")
        assert arg is not None
        assert arg.model_var_kind_mismatch is not None
        # Annotation format is "scheme_kind:host_kind"
        mismatch = arg.model_var_kind_mismatch.data
        assert "kind_phys" in mismatch
        assert "kind_dyn" in mismatch

    def test_matching_kinds_no_annotation(self, run_host_match):
        """When kinds match, no model_var_kind_mismatch annotation is set."""
        module = run_host_match(
            scheme_metas=[scheme_meta("test_scheme", SCHEME_REAL_VAR)],
            host_metas=[host_meta("test_mod", HOST_REAL_VAR)],
        )
        arg = _get_scheme_arg(module, "test_scheme", "some_variable")
        assert arg is not None
        assert arg.model_var_kind_mismatch is None


class TestDimensionCompatibility:
    """Dimension names within the same CCPP equivalence class are compatible."""

    def _make_pair(self, scheme_dim: str, host_dim: str) -> tuple:
        scheme = scheme_meta("test_scheme", f"""\
[ var_a ]
  standard_name = some_variable
  type = real
  kind = kind_phys
  intent = inout
  dimensions = ({scheme_dim})
  units = K
""")
        host = host_meta("test_mod", f"""\
[ host_var_a ]
  standard_name = some_variable
  type = real
  kind = kind_phys
  dimensions = ({host_dim})
  units = K
""")
        return scheme, host

    def test_horizontal_loop_extent_to_horizontal_dimension(self, run_host_match):
        """horizontal_loop_extent (scheme) → horizontal_dimension (host) is valid."""
        scheme, host = self._make_pair("horizontal_loop_extent", "horizontal_dimension")
        run_host_match(scheme_metas=[scheme], host_metas=[host])

    def test_horizontal_dimension_to_horizontal_loop_extent(self, run_host_match):
        """Reverse: horizontal_dimension (scheme) → horizontal_loop_extent (host) is valid."""
        scheme, host = self._make_pair("horizontal_dimension", "horizontal_loop_extent")
        run_host_match(scheme_metas=[scheme], host_metas=[host])

    def test_vertical_layer_to_interface_dimension(self, run_host_match):
        """vertical_layer_dimension ↔ vertical_interface_dimension are compatible."""
        scheme, host = self._make_pair(
            "vertical_layer_dimension", "vertical_interface_dimension"
        )
        run_host_match(scheme_metas=[scheme], host_metas=[host])

    def test_vertical_interface_to_layer_dimension(self, run_host_match):
        """Reverse: vertical_interface_dimension ↔ vertical_layer_dimension."""
        scheme, host = self._make_pair(
            "vertical_interface_dimension", "vertical_layer_dimension"
        )
        run_host_match(scheme_metas=[scheme], host_metas=[host])

    def test_range_form_horizontal_compatibility(self, run_host_match):
        """ccpp_constant_one:horizontal_loop_extent ↔ horizontal_dimension."""
        scheme, host = self._make_pair(
            "ccpp_constant_one:horizontal_loop_extent", "horizontal_dimension"
        )
        run_host_match(scheme_metas=[scheme], host_metas=[host])

    def test_range_form_horizontal_same_class(self, run_host_match):
        """ccpp_constant_one:horizontal_loop_extent ↔ horizontal_loop_extent."""
        scheme, host = self._make_pair(
            "ccpp_constant_one:horizontal_loop_extent", "horizontal_loop_extent"
        )
        run_host_match(scheme_metas=[scheme], host_metas=[host])

    def test_2d_mixed_horizontal_vertical(self, run_host_match):
        """2-D: scheme uses (horizontal_loop_extent, vertical_layer_dimension),
        host uses (horizontal_dimension, vertical_interface_dimension)."""
        scheme = scheme_meta("test_scheme", """\
[ var_a ]
  standard_name = some_variable
  type = real
  kind = kind_phys
  intent = inout
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  units = K
""")
        host = host_meta("test_mod", """\
[ host_var_a ]
  standard_name = some_variable
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension, vertical_interface_dimension)
  units = K
""")
        run_host_match(scheme_metas=[scheme], host_metas=[host])

    def test_incompatible_horizontal_vs_vertical_raises(self, run_host_match):
        """A horizontal dimension is NOT compatible with a vertical one."""
        scheme, host = self._make_pair(
            "horizontal_dimension", "vertical_layer_dimension"
        )
        with pytest.raises(ValueError, match="dimension.*mismatch"):
            run_host_match(scheme_metas=[scheme], host_metas=[host])

    def test_exact_match_still_works(self, run_host_match):
        """Identical dimension names on both sides remain compatible."""
        scheme, host = self._make_pair("horizontal_dimension", "horizontal_dimension")
        run_host_match(scheme_metas=[scheme], host_metas=[host])


class TestMissingVariables:

    def test_missing_required_var_raises(self, run_host_match):
        """Scheme requires a variable the host does not provide → error."""
        scheme = scheme_meta("test_scheme", """\
[ var_unknown ]
  standard_name = no_such_variable_in_host
  type = real
  kind = kind_phys
  intent = in
  dimensions = ()
  units = K
""")
        with pytest.raises(ValueError, match="no matching host model variable"):
            run_host_match(
                scheme_metas=[scheme],
                host_metas=[host_meta("test_mod", HOST_REAL_VAR)],
            )

    def test_all_errors_collected_before_raise(self, run_host_match):
        """All missing-variable errors are reported together, not one at a time."""
        scheme = scheme_meta("test_scheme", """\
[ var_missing_1 ]
  standard_name = missing_variable_one
  type = real
  intent = in
  dimensions = ()
  units = K
[ var_missing_2 ]
  standard_name = missing_variable_two
  type = real
  intent = in
  dimensions = ()
  units = K
""")
        with pytest.raises(ValueError) as exc_info:
            run_host_match(
                scheme_metas=[scheme],
                host_metas=[host_meta("test_mod", HOST_REAL_VAR)],
            )
        msg = str(exc_info.value)
        assert "missing_variable_one" in msg
        assert "missing_variable_two" in msg
