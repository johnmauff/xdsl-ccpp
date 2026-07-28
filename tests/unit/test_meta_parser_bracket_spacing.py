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
"""

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
