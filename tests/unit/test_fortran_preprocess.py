"""Unit tests for fortran_preprocess -- CPP directive support for Fortran
source text feeding fparser2_to_meta's extraction pipeline.

See fortran_preprocess.py's own module docstring for the design (mirrors
capgen-v1's PreprocStack, written fresh) and the two deliberate departures
from capgen-v1's own semantics this file locks in via tests 8 and 5.
"""

import pytest

from xdsl_ccpp.transforms.fortran_preprocess import (
    parse_preproc_defines,
    preprocess_fortran_source,
)


# ── parse_preproc_defines ────────────────────────────────────────────────────

class TestParsePreprocDefines:
    def test_mixed_forms(self):
        assert parse_preproc_defines(["-DSPMD", "NP=4", "-D_MPI"]) == {
            "SPMD": None,
            "NP": "4",
            "_MPI": None,
        }

    def test_empty_and_none(self):
        assert parse_preproc_defines([]) == {}
        assert parse_preproc_defines(None) == {}

    def test_blank_entries_ignored(self):
        assert parse_preproc_defines(["", "  ", "FOO"]) == {"FOO": None}

    def test_dash_d_equals(self):
        assert parse_preproc_defines(["-DNP=8"]) == {"NP": "8"}


# ── #ifdef / #ifndef ─────────────────────────────────────────────────────────

class TestIfdef:
    def test_true_branch(self):
        src = "before\n#ifdef FOO\nyes\n#endif\nafter\n"
        out = preprocess_fortran_source(src, "t.F90", {"FOO": None})
        assert "yes" in out
        assert out.splitlines()[0] == "before"
        assert out.splitlines()[-1] == "after"

    def test_false_branch_blanked_not_deleted(self):
        src = "before\n#ifdef FOO\nyes\n#endif\nafter\n"
        out = preprocess_fortran_source(src, "t.F90", {})
        lines = out.splitlines()
        assert len(lines) == len(src.splitlines())
        assert "yes" not in out

    def test_ifndef_true_when_undefined(self):
        src = "#ifndef FOO\nyes\n#endif\n"
        assert "yes" in preprocess_fortran_source(src, "t.F90", {})

    def test_ifndef_false_when_defined(self):
        src = "#ifndef FOO\nyes\n#endif\n"
        assert "yes" not in preprocess_fortran_source(src, "t.F90", {"FOO": None})


class TestElse:
    def test_else_fires_when_condition_false(self):
        src = "#ifdef FOO\na\n#else\nb\n#endif\n"
        out = preprocess_fortran_source(src, "t.F90", {})
        assert "b" in out
        assert "a" not in out

    def test_else_does_not_fire_when_condition_true(self):
        src = "#ifdef FOO\na\n#else\nb\n#endif\n"
        out = preprocess_fortran_source(src, "t.F90", {"FOO": None})
        assert "a" in out
        assert "b" not in out


class TestNestedConditionals:
    def test_inner_evaluated_when_outer_true(self):
        src = "#ifdef OUTER\n#if NP == 4\nfour\n#else\nother\n#endif\n#endif\n"
        out = preprocess_fortran_source(src, "t.F90", {"OUTER": None, "NP": "4"})
        assert "four" in out
        assert "other" not in out

    def test_inner_never_evaluated_when_outer_false(self):
        # OUTER is undefined, so the #if NP == 4 line is inside a dead
        # region -- NP being entirely absent from defines must not raise,
        # since the inner condition is never actually evaluated.
        src = "#ifdef OUTER\n#if NP == 4\nfour\n#endif\n#endif\nsafe\n"
        out = preprocess_fortran_source(src, "t.F90", {})
        assert "four" not in out
        assert "safe" in out


class TestIfElifNumeric:
    @pytest.mark.parametrize(
        "np_value,expected",
        [("4", "four"), ("8", "eight"), ("16", "other")],
    )
    def test_elif_chain(self, np_value, expected):
        src = (
            "#if NP == 4\nfour\n#elif NP == 8\neight\n#else\nother\n#endif\n"
        )
        out = preprocess_fortran_source(src, "t.F90", {"NP": np_value})
        for branch in ("four", "eight", "other"):
            if branch == expected:
                assert branch in out
            else:
                assert branch not in out


class TestUndefinedSymbol:
    def test_bare_undefined_value_is_falsy(self):
        # Deliberate departure from capgen-v1 (module docstring #1): an
        # undefined identifier used as a bare value in #if evaluates to 0,
        # matching real CPP -- not the identifier string capgen-v1 itself
        # would substitute.
        src = "#if UNDEFINED_SYM\nyes\n#endif\n"
        assert "yes" not in preprocess_fortran_source(src, "t.F90", {})

    def test_defined_check_unaffected(self):
        src = "#if defined(UNDEFINED_SYM)\nyes\n#endif\n"
        assert "yes" not in preprocess_fortran_source(src, "t.F90", {})
        src2 = "#if defined(FOO)\nyes\n#endif\n"
        assert "yes" in preprocess_fortran_source(src2, "t.F90", {"FOO": None})

    def test_bare_define_numeric_coercion(self):
        # Departure #2: a string-valued define ('4') compares correctly
        # against an integer literal via numeric coercion.
        src = "#if NP == 4\nyes\n#endif\n"
        assert "yes" in preprocess_fortran_source(src, "t.F90", {"NP": "4"})


class TestMalformedDirectives:
    def test_stray_else(self):
        with pytest.raises(ValueError, match=r"t\.F90:1: '#else'"):
            preprocess_fortran_source("#else\n", "t.F90", {})

    def test_stray_endif(self):
        with pytest.raises(ValueError, match=r"t\.F90:1: '#endif'"):
            preprocess_fortran_source("#endif\n", "t.F90", {})

    def test_stray_elif(self):
        with pytest.raises(ValueError, match=r"t\.F90:1: '#elif'"):
            preprocess_fortran_source("#elif FOO\n", "t.F90", {})

    def test_elif_after_else(self):
        src = "#ifdef FOO\na\n#else\nb\n#elif BAR\nc\n#endif\n"
        with pytest.raises(ValueError, match=r"'#elif' after '#else'"):
            preprocess_fortran_source(src, "t.F90", {})

    def test_duplicate_else(self):
        src = "#ifdef FOO\na\n#else\nb\n#else\nc\n#endif\n"
        with pytest.raises(ValueError, match=r"duplicate '#else'"):
            preprocess_fortran_source(src, "t.F90", {})

    def test_unterminated_ifdef(self):
        with pytest.raises(ValueError, match=r"unterminated '#ifdef FOO'.*line 1"):
            preprocess_fortran_source("#ifdef FOO\nx\n", "t.F90", {"FOO": None})


class TestLineNumbersPreserved:
    def test_error_after_excluded_region_names_correct_line(self):
        src = "\n".join(
            [
                "line1",
                "#ifdef NEVER",
                "excluded1",
                "excluded2",
                "excluded3",
                "#endif",
                "#endif",  # deliberate stray directive at line 7
            ]
        ) + "\n"
        with pytest.raises(ValueError, match=r"t\.F90:7: '#endif'"):
            preprocess_fortran_source(src, "t.F90", {})

    def test_output_line_count_matches_input(self):
        src = "a\n#ifdef FOO\nb\nc\n#else\nd\n#endif\ne\n"
        out = preprocess_fortran_source(src, "t.F90", {})
        assert len(out.splitlines()) == len(src.splitlines())


class TestDoesNotMutateCallerDict:
    def test_define_undef_scoped_to_call(self):
        defines = {"FOO": None}
        preprocess_fortran_source("#define BAR 1\n", "t.F90", defines)
        assert defines == {"FOO": None}

    def test_define_inside_true_region_only(self):
        src = "#ifdef FOO\n#define BAR\n#endif\n#ifdef BAR\nyes\n#endif\n"
        # FOO undefined: #define BAR must not take effect
        assert "yes" not in preprocess_fortran_source(src, "t.F90", {})
        assert "yes" in preprocess_fortran_source(src, "t.F90", {"FOO": None})
