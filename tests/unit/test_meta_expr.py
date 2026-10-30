"""The ``.meta`` expression parser (active-condition-ir): ``active``
properties and subscripted host local names parse into a syntax tree, and
malformed ones are rejected with the file and line."""

import pytest

from xdsl_ccpp.frontend.ccpp_xml import parse_meta_file
from xdsl_ccpp.frontend.meta_expr import (
    Binary,
    FullSlice,
    IntLiteral,
    LogicalLiteral,
    MetaExprError,
    Name,
    Not,
    SubscriptedName,
    parse_active_expr,
    parse_local_name,
    standard_names,
)


@pytest.mark.parametrize("text, tree", [
    ("flag_for_opt_arg", Name("flag_for_opt_arg")),
    ("(flag_for_opt_array)", Name("flag_for_opt_array")),
    ("(index_of_water_vapor_specific_humidity > 0)",
     Binary("gt", Name("index_of_water_vapor_specific_humidity"), IntLiteral(0))),
    ("Flag_A .AND. .not. flag_b",
     Binary("and", Name("flag_a"), Not(Name("flag_b")))),
    ("a .or. b .and. c", Binary("or", Name("a"), Binary("and", Name("b"), Name("c")))),
    ("(a .or. b) .and. c", Binary("and", Binary("or", Name("a"), Name("b")), Name("c"))),
    ("n /= 3 .eqv. .true.",
     Binary("eqv", Binary("ne", Name("n"), IntLiteral(3)), LogicalLiteral(True))),
    ("n .ge. 1", Binary("ge", Name("n"), IntLiteral(1))),
    ("a .neqv. b .or. c", Binary("neqv", Name("a"), Binary("or", Name("b"), Name("c")))),
])
def test_active_expressions(text, tree):
    assert parse_active_expr(text) == tree


@pytest.mark.parametrize("text", [
    "", "(a", "a)", "a > ", "a > 0 > 1", "a .xor. b", "a && b", "a .and.", "f(x)",
    "1.5 > a",
])
def test_malformed_active_expressions(text):
    with pytest.raises(MetaExprError):
        parse_active_expr(text)


def test_error_names_the_column():
    with pytest.raises(MetaExprError, match=r"unexpected character '&' at column 3"):
        parse_active_expr("a && b")


@pytest.mark.parametrize("text, tree", [
    ("q", SubscriptedName("q")),
    ("q(:,:,index_of_water_vapor_specific_HUMidity)",
     SubscriptedName("q", (FullSlice(), FullSlice(),
                           Name("index_of_water_vapor_specific_humidity")))),
    ("data_array(:, 1)", SubscriptedName("data_array", (FullSlice(), IntLiteral(1)))),
])
def test_local_names(text, tree):
    assert parse_local_name(text) == tree


@pytest.mark.parametrize("text", ["q(", "q()", "q(:,)", "q(a > 0)", "q(1:2)", "a%b", "1q"])
def test_malformed_local_names(text):
    with pytest.raises(MetaExprError):
        parse_local_name(text)


def test_standard_names_in_order():
    tree = parse_active_expr("b .and. (a > n) .or. b")
    assert standard_names(tree) == ["b", "a", "n"]


_META = """\
[ccpp-table-properties]
  name = host_mod
  type = module
[ccpp-arg-table]
  name = host_mod
  type = module
[ {name} ]
  standard_name = some_var
  units = 1
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension)
  active = {active}
"""


@pytest.mark.parametrize("name, active, line", [
    ("x", "(flag > )", 12),
    ("x(:,", "flag", 7),
])
def test_frontend_reports_file_and_line(tmp_path, name, active, line):
    meta = tmp_path / "host_mod.meta"
    meta.write_text(_META.format(name=name, active=active))
    with pytest.raises(ValueError, match=rf"host_mod\.meta:{line}: "):
        parse_meta_file(str(meta), is_scheme=False)


def test_frontend_accepts_valid_expressions(tmp_path):
    meta = tmp_path / "host_mod.meta"
    meta.write_text(_META.format(name="q(:, index_of_x)", active="(n > 0) .and. flag"))
    (table,) = parse_meta_file(str(meta), is_scheme=False)
    assert table is not None
