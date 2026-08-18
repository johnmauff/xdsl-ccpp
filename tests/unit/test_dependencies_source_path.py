"""Unit tests for metadata ``dependencies``/``dependencies_path``/``source_path``
tracking (Tier 1 of ccpp_cap_refactor_plan.md's "dependencies/source_path
tracking" entry).

Real capgen-v1 (``metadata/metadata_table.py``'s ``MetadataTable.apply_table_props``)
supports these three ``[ccpp-table-properties]`` keys to locate a scheme's real
Fortran source and any extra files it depends on. xdsl-ccpp previously: accepted
``dependencies`` but never forwarded it anywhere; didn't accept ``source_path``
at all (a real upstream ``.meta`` file declaring it would crash the parser);
and accepted a nonstandard ``relative_path`` key instead of the real
``dependencies_path`` name. This restores the real key names and forwards all
three onto ``TablePropertiesOp``'s IR attributes -- deliberately *not*
resolving them to filesystem paths (no code consumes them for that yet, see
the backlog entry's own "Tier 2" note).
"""

import pytest
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp


def _table_properties_op(module):
    for op in module.body.ops:
        if isa(op, ccpp.TablePropertiesOp):
            return op
    raise AssertionError("no ccpp.table_properties op found")


class TestDependenciesParsing:
    def test_single_dependency(self, build_module):
        module = build_module(
            [
                "[ccpp-table-properties]\n"
                "  name = scheme_a\n"
                "  type = scheme\n"
                "  dependencies = util.F90\n"
                "[ccpp-arg-table]\n"
                "  name = scheme_a_run\n"
                "  type = scheme\n"
            ],
            [], None,
        )
        op = _table_properties_op(module)
        deps = op.attributes.get("dependencies")
        assert [d.data for d in deps.data] == ["util.F90"]

    def test_comma_separated_dependencies(self, build_module):
        module = build_module(
            [
                "[ccpp-table-properties]\n"
                "  name = scheme_a\n"
                "  type = scheme\n"
                "  dependencies = foo.F90, bar.F90\n"
                "[ccpp-arg-table]\n"
                "  name = scheme_a_run\n"
                "  type = scheme\n"
            ],
            [], None,
        )
        op = _table_properties_op(module)
        deps = op.attributes.get("dependencies")
        assert [d.data for d in deps.data] == ["foo.F90", "bar.F90"]

    def test_repeated_dependencies_key_accumulates(self, build_module):
        """Real capgen-v1 allows `dependencies` to appear more than once in
        one table-properties block, accumulating rather than overwriting."""
        module = build_module(
            [
                "[ccpp-table-properties]\n"
                "  name = scheme_a\n"
                "  type = scheme\n"
                "  dependencies = foo.F90\n"
                "  dependencies = bar.F90\n"
                "[ccpp-arg-table]\n"
                "  name = scheme_a_run\n"
                "  type = scheme\n"
            ],
            [], None,
        )
        op = _table_properties_op(module)
        deps = op.attributes.get("dependencies")
        assert [d.data for d in deps.data] == ["foo.F90", "bar.F90"]

    def test_empty_dependencies_declares_none(self, build_module):
        """`dependencies =` with nothing after it (real capgen-v1's own
        temp_calc_adjust.meta shape) means "explicitly no dependencies", not
        a single empty-string dependency."""
        module = build_module(
            [
                "[ccpp-table-properties]\n"
                "  name = scheme_a\n"
                "  type = scheme\n"
                "  dependencies =\n"
                "[ccpp-arg-table]\n"
                "  name = scheme_a_run\n"
                "  type = scheme\n"
            ],
            [], None,
        )
        op = _table_properties_op(module)
        assert op.attributes.get("dependencies") is None

    def test_none_sentinel_is_skipped(self, build_module):
        """Real capgen-v1's own "none" sentinel for an explicit empty
        dependency set (distinct from a genuinely empty value)."""
        module = build_module(
            [
                "[ccpp-table-properties]\n"
                "  name = scheme_a\n"
                "  type = scheme\n"
                "  dependencies = none\n"
                "[ccpp-arg-table]\n"
                "  name = scheme_a_run\n"
                "  type = scheme\n"
            ],
            [], None,
        )
        op = _table_properties_op(module)
        assert op.attributes.get("dependencies") is None


class TestSourcePathAndDependenciesPath:
    def test_source_path_is_accepted_and_forwarded(self, build_module):
        module = build_module(
            [
                "[ccpp-table-properties]\n"
                "  name = scheme_a\n"
                "  type = scheme\n"
                "  source_path = source_dir2\n"
                "[ccpp-arg-table]\n"
                "  name = scheme_a_run\n"
                "  type = scheme\n"
            ],
            [], None,
        )
        op = _table_properties_op(module)
        assert op.attributes.get("source_path").data == "source_dir2"

    def test_dependencies_path_is_accepted_and_forwarded(self, build_module):
        module = build_module(
            [
                "[ccpp-table-properties]\n"
                "  name = scheme_a\n"
                "  type = scheme\n"
                "  dependencies_path = adjust\n"
                "  dependencies = temp_kinds.F90\n"
                "[ccpp-arg-table]\n"
                "  name = scheme_a_run\n"
                "  type = scheme\n"
            ],
            [], None,
        )
        op = _table_properties_op(module)
        assert op.attributes.get("dependencies_path").data == "adjust"
        assert [d.data for d in op.attributes.get("dependencies").data] == ["temp_kinds.F90"]

    def test_relative_path_is_no_longer_a_valid_key(self, build_module):
        """The old, nonstandard key this codebase used to accept in place of
        the real dependencies_path -- confirms it's genuinely gone, not just
        silently ignored."""
        with pytest.raises(AssertionError):
            build_module(
                [
                    "[ccpp-table-properties]\n"
                    "  name = scheme_a\n"
                    "  type = scheme\n"
                    "  relative_path = adjust\n"
                    "[ccpp-arg-table]\n"
                    "  name = scheme_a_run\n"
                    "  type = scheme\n"
                ],
                [], None,
            )
