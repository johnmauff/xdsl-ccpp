"""xdsl_ccpp.tools.verify_py_suites: a Python suite is checked against the
XML suite of the same name after flattening."""

import io
import json

from xdsl_ccpp.tools.verify_py_suites import _explained, _explained_json, verify

_ERR = """[ errmsg ]
  standard_name = ccpp_error_message
  units = none
  dimensions = ()
  type = character
  kind = len=512
  intent = out
[ errflg ]
  standard_name = ccpp_error_code
  units = 1
  dimensions = ()
  type = integer
  intent = out
"""


def _meta(name, phases):
    tables = "".join(f"""[ccpp-arg-table]
  name = {name}_{phase}
  type = scheme
{_ERR}""" for phase in phases)
    return f"""[ccpp-table-properties]
  name = {name}
  type = scheme
{tables}"""


def _xml(schemes):
    body = "".join(f"    <scheme>{s}</scheme>\n" for s in schemes)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<suite name="demo" version="1.0">
  <group name="physics">
{body}  </group>
</suite>
"""


def _py(schemes):
    refs = "".join(f'{s} = ccpp_scheme_ref("{s}")\n' for s in dict.fromkeys(schemes))
    calls = "".join(f"        {s}()\n" for s in schemes)
    return f"""from xdsl_ccpp.frontend.py_api import ccpp_scheme_ref, ccpp_suite, export_suite
from helpers import physics_step
{refs}
@ccpp_suite("demo", version="1.0")
class Demo:
    def physics():
{calls}
if __name__ == "__main__":
    export_suite(Demo)
"""


def _run(tmp_path, xml_schemes, py_schemes, strict=False):
    for d in ("py", "xml", "schemes", "lib"):
        (tmp_path / d).mkdir(exist_ok=True)
    for name, phases in {"a": ["run"], "b": ["run"], "c": ["run"],
                         "opts": ["init"]}.items():
        (tmp_path / "schemes" / f"{name}.meta").write_text(_meta(name, phases))
    (tmp_path / "xml" / "suite_demo.xml").write_text(_xml(xml_schemes))
    (tmp_path / "py" / "suite_demo.py").write_text(_py(py_schemes))
    # A helper module the suite imports, found only through --import-path.
    (tmp_path / "lib" / "helpers.py").write_text("physics_step = None\n")
    out = io.StringIO()
    ok = verify([str(tmp_path / "py")], [str(tmp_path / "xml")],
                [str(tmp_path / "schemes")], [str(tmp_path / "lib")],
                strict=strict, out=out)
    return ok, out.getvalue()


def test_identical_suites_pass(tmp_path):
    ok, out = _run(tmp_path, ["opts", "a", "b", "c"], ["opts", "a", "b", "c"])
    assert ok and out.strip() == "demo: PASS", out


def test_reordered_run_schemes_fail(tmp_path):
    ok, out = _run(tmp_path, ["a", "b", "c"], ["a", "c", "b"])
    assert not ok and "demo: FAIL" in out and "item 1" in out, out


def test_moved_init_only_scheme_passes_with_a_note(tmp_path):
    ok, out = _run(tmp_path, ["opts", "a", "b", "c"], ["a", "opts", "b", "c"])
    assert ok and "demo: PASS (moved init-only schemes: opts)" in out, out


def test_moved_init_only_scheme_fails_when_strict(tmp_path):
    ok, out = _run(tmp_path, ["opts", "a", "b"], ["a", "opts", "b"], strict=True)
    assert not ok and "--strict" in out, out


def test_missing_scheme_fails(tmp_path):
    ok, out = _run(tmp_path, ["a", "b", "c"], ["a", "b"])
    assert not ok and "demo: FAIL" in out, out


def test_unmatched_suites_are_reported(tmp_path):
    _run(tmp_path, ["a"], ["a"])
    (tmp_path / "xml" / "suite_extra.xml").write_text(_xml(["a"]))
    (tmp_path / "py" / "suite_lonely.py").write_text(_py(["a"]))
    out = io.StringIO()
    verify([str(tmp_path / "py")], [str(tmp_path / "xml")], [str(tmp_path / "schemes")],
           [str(tmp_path / "lib")], out=out)
    text = out.getvalue()
    assert "lonely: no XML suite to compare with" in text
    assert "XML suites with no Python form: extra" in text


# --case: which differences between caps generated from the two forms are
# accepted (classified), on small synthetic files.

_CAP = """module demo_cap
contains
  subroutine demo_init_physics(masterproc, opt_a, errmsg, errflg)
    call opts_init(masterproc=masterproc)
  end subroutine demo_init_physics
  subroutine demo_physics(col_start, col_end, x, errmsg, errflg)
    call a_run(x=x)
  end subroutine demo_physics
  subroutine ccpp_physics_suite_schemes(scheme_list)
    scheme_list(1) = 'opts'
    scheme_list(2) = 'a'
  end subroutine ccpp_physics_suite_schemes
end module demo_cap"""


def _lines(text, *swaps):
    for old, new in swaps:
        text = text.replace(old, new)
    return text.splitlines()


def test_init_routine_and_scheme_list_differences_need_moved_schemes():
    py = _lines(_CAP, ("masterproc, opt_a", "opt_a, amIRoot"),
                ("masterproc=masterproc", "masterproc=amIRoot"),
                ("(1) = 'opts'", "(1) = 'a'"), ("(2) = 'a'", "(2) = 'opts'"))
    ok, kinds = _explained(_CAP.splitlines(), py, [], set(), ["opts"])
    assert ok and kinds == {"init routines (moved init-only schemes)",
                            "scheme list order (moved init-only schemes)"}
    assert not _explained(_CAP.splitlines(), py, [], set(), [])[0]


def test_run_routine_differences_are_not_explained():
    py = _lines(_CAP, ("call a_run(x=x)", "call a_run(x=y)"))
    assert not _explained(_CAP.splitlines(), py, [], set(), ["opts"])[0]


def test_package_prefixes_are_explained():
    py = _lines(_CAP, ("x=x", "x=pkg__x"))
    ok, kinds = _explained(_CAP.splitlines(), py, ["pkg"], {"x"}, [])
    assert ok and kinds == {"package-private names"}


def test_resolved_vars_order_and_names():
    def rv(*init, run=("t",)):
        entry = lambda n, a: {"standard_name": n, "arg_name": a}
        return json.dumps({"phases": {"initialize": [entry(n, a) for n, a in init],
                                      "run": [entry(n, n) for n in run]},
                           "host_vars": []}, indent=1).splitlines()
    xml = rv(("flag", "masterproc"), ("w", "w"))
    py = rv(("pkg__w", "w"), ("flag", "amIRoot"))
    ok, kinds = _explained_json(xml, py, ["pkg"], ["opts"])
    assert ok and kinds == {"package-private names",
                            "initialize entry order (moved init-only schemes)"}
    assert not _explained_json(xml, py, ["pkg"], [])[0]
    assert not _explained_json(xml, rv(("flag", "masterproc"), ("w", "w"), run=("u",)),
                               [], ["opts"])[0]
