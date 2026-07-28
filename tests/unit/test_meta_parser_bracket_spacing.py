"""Unit tests for parse_meta_file's argument-bracket spacing tolerance.

Backlog item: "``.meta`` argument-bracket parser requires exact spacing
(``[ name ]``, not ``[name]``) to tell an argument name apart from an
unrecognized token" (ccpp_cap_refactor_plan.md).

Root cause: ccpp_xml.py's parse_meta_file disambiguated an argument-name
bracket from an unrecognized token purely by checking whether the bracket's
contents had a leading or trailing space (``token[0] == " " or
token[-1] == " "``) -- this project's own writer convention always emits the
spaced form, but capgen-v1's own upstream ``.meta`` files (var_compat's
effr_pre.meta/effr_calc.meta/etc., 14+ occurrences) use the tight
``[effrr_in]`` form with no such requirement. A tight-form argument bracket
fell through to the ``else`` branch and raised
``AssertionError("Unexpected token in arg table: ...")``, forcing every
ported ``.meta`` file to be manually reformatted to the spaced form (see
examples/var_compat/README.md's "Adaptations made during porting" section).

Fixed by dropping the space-heuristic condition entirely: by the point
execution reaches that branch, the token is already known not to be one of
the two recognized headers (``ccpp-table-properties``/``ccpp-arg-table``),
and a ``.meta`` file's grammar has no other bracketed construct -- so any
remaining bracketed token is unambiguously an argument name, spaced or not.

Follow-up (found by Copilot's review of that fix, PR #46): turning the old
space-heuristic ``elif``/``else`` pair into a single unconditional ``else``
also removed the only remaining validation in that branch. Two malformed-
input cases would previously have crashed confusingly rather than raising a
clear error pointing at the actual mistake:

1. An argument-shaped bracket appearing before any ``[ccpp-arg-table]``
   header (``current_arg_table`` still ``None``) wouldn't fail immediately --
   the crash only surfaced the *next* time a bracket was encountered, when
   the pending argument was attached to a still-nonexistent table
   (``AttributeError: 'NoneType' object has no attribute
   'setFunctionArgument'``), far from the line with the actual mistake.
2. An empty or whitespace-only bracket (``[]``) would silently become an
   argument with an empty name (``CCPPArgument("")``) instead of being
   rejected, propagating a nameless argument downstream.

Fixed by validating both explicitly, with a ``ValueError`` naming the file
and line number, right at the point the raw ``.meta`` text is parsed (a
system boundary -- these are external, user-authored files).
"""

import pytest

from xdsl_ccpp.frontend.ccpp_xml import parse_meta_file

_TIGHT_META = """\
[ccpp-table-properties]
  name = tight_scheme
  type = scheme
[ccpp-arg-table]
  name = tight_scheme_run
  type = scheme
[x]
  standard_name = some_var
  units = m
  type = real
  kind = kind_phys
  dimensions = ()
  intent = in
[errmsg]
  standard_name = ccpp_error_message
  long_name = Error message for error handling in CCPP
  units = none
  dimensions = ()
  type = character
  kind = len=512
  intent = out
[errflg]
  standard_name = ccpp_error_code
  long_name = Error flag for error handling in CCPP
  units = 1
  dimensions = ()
  type = integer
  intent = out
"""

_SPACED_META = """\
[ccpp-table-properties]
  name = spaced_scheme
  type = scheme
[ccpp-arg-table]
  name = spaced_scheme_run
  type = scheme
[ x ]
  standard_name = some_var
  units = m
  type = real
  kind = kind_phys
  dimensions = ()
  intent = in
[ errmsg ]
  standard_name = ccpp_error_message
  long_name = Error message for error handling in CCPP
  units = none
  dimensions = ()
  type = character
  kind = len=512
  intent = out
[ errflg ]
  standard_name = ccpp_error_code
  long_name = Error flag for error handling in CCPP
  units = 1
  dimensions = ()
  type = integer
  intent = out
"""


def _arg_names(tables) -> list:
    names = []
    for md in tables:
        for table in md.arg_tables:
            for arg in table.getFunctionArguments():
                names.append(arg.name)
    return names


class TestTightBracketArgumentName:
    def test_tight_form_parses_without_error(self, tmp_path):
        meta_file = tmp_path / "tight.meta"
        meta_file.write_text(_TIGHT_META)
        tables = parse_meta_file(str(meta_file), True)
        assert _arg_names(tables) == ["x", "errmsg", "errflg"]

    def test_tight_and_spaced_forms_produce_identical_arg_names(self, tmp_path):
        tight_file = tmp_path / "tight.meta"
        tight_file.write_text(_TIGHT_META)
        spaced_file = tmp_path / "spaced.meta"
        spaced_file.write_text(_SPACED_META)

        assert _arg_names(parse_meta_file(str(tight_file), True)) == _arg_names(
            parse_meta_file(str(spaced_file), True)
        )


_ARG_BEFORE_ARG_TABLE_META = """\
[ccpp-table-properties]
  name = bad_scheme
  type = scheme
[x]
  standard_name = some_var
[ccpp-arg-table]
  name = bad_scheme_run
  type = scheme
"""

_EMPTY_ARG_NAME_META = """\
[ccpp-table-properties]
  name = bad_scheme2
  type = scheme
[ccpp-arg-table]
  name = bad_scheme2_run
  type = scheme
[]
  standard_name = some_var
"""


class TestArgumentBeforeArgTableHeaderRejected:
    """[x] appears right after [ccpp-table-properties] but before the first
    [ccpp-arg-table] -- current_arg_table is still None at that point.
    Before this fix, this didn't fail here at all; it silently set
    current_arg and only crashed later (AttributeError, on an unrelated
    line) the next time a bracket was seen and the code tried to attach the
    pending argument to a still-nonexistent table."""

    def test_raises_clear_error_naming_file_and_line(self, tmp_path):
        meta_file = tmp_path / "bad.meta"
        meta_file.write_text(_ARG_BEFORE_ARG_TABLE_META)
        with pytest.raises(ValueError, match=r"bad\.meta:4.*before any \[ccpp-arg-table\]"):
            parse_meta_file(str(meta_file), True)


class TestEmptyArgumentNameRejected:
    """[] (or whitespace-only brackets) would otherwise silently become
    CCPPArgument("") -- a nameless argument propagated downstream instead
    of being rejected at the parse boundary."""

    def test_raises_clear_error_naming_file_and_line(self, tmp_path):
        meta_file = tmp_path / "bad2.meta"
        meta_file.write_text(_EMPTY_ARG_NAME_META)
        with pytest.raises(ValueError, match=r"bad2\.meta:7.*empty argument name"):
            parse_meta_file(str(meta_file), True)
