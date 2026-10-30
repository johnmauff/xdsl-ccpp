"""code_coverage.py's report helpers (dead-code-coverage): function bodies
from the AST, and runs of unreached statements."""

from xdsl_ccpp.tools.code_coverage import _blocks, _functions

_SOURCE = '''\
def outer(x):
    y = x + 1

    def inner():
        return y

    return inner


class K:
    def method(self):
        if self:
            return 1
        return 2
'''


def test_functions_exclude_nested_bodies(tmp_path):
    path = tmp_path / "m.py"
    path.write_text(_SOURCE)
    found = {name: (line, body) for name, line, body in _functions(str(path))}
    assert sorted(found) == ["K.method", "outer", "outer.inner"]
    outer_line, outer_body = found["outer"]
    assert outer_line == 1
    assert 5 not in outer_body
    assert {2, 4, 7} <= outer_body
    assert found["outer.inner"][1] == {5}
    assert found["K.method"][1] == {12, 13, 14}


def test_blocks_follow_statement_order():
    statements = [2, 3, 5, 8, 9, 10]
    assert _blocks([3, 5, 9, 10], statements) == [[3, 5], [9, 10]]
    assert _blocks([], statements) == []
