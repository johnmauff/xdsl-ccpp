"""xdsl_ccpp.tools.py2sdf: a Python suite written as a suite definition file
defines the same suite once read back."""

import io
import xml.etree.ElementTree as ET

import pytest

from xdsl_ccpp.tools.py2sdf import main, py_to_sdf
from xdsl_ccpp.tools.verify_py_suites import verify

# A package with a hook, a loop counted by a standard name, and a second
# group: what py2sdf has to flatten.
_SUITE = """\
from xdsl_ccpp.frontend.py_api import (ccpp_package, ccpp_scheme_ref, ccpp_suite,
                                       export_suite, forLoop)

a = ccpp_scheme_ref("a")
b = ccpp_scheme_ref("b")
c = ccpp_scheme_ref("c")
pkg = ccpp_package("pkg")

@pkg.entry_point
def step(*, hook):
    a()
    with forLoop("number_of_subcycles"):
        hook()
        b()

@ccpp_suite("demo", version="1.0")
class Demo:
    def physics():
        step(hook=c)
    def after():
        c()

if __name__ == "__main__":
    export_suite(Demo)
"""

_META = """[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_run
  type = scheme
[ errmsg ]
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


def _suite_file(tmp_path, text=_SUITE):
    (tmp_path / "py").mkdir(exist_ok=True)
    path = tmp_path / "py" / "suite_demo.py"
    path.write_text(text)
    return path


def test_flattened_suite_is_written_as_xml(tmp_path):
    xml = py_to_sdf(str(_suite_file(tmp_path)))["demo"]
    root = ET.fromstring(xml.split("\n", 2)[2])
    assert (root.tag, root.get("name"), root.get("version")) == ("suite", "demo", "1.0")
    physics, after = root.findall("group")
    assert [physics.get("name"), after.get("name")] == ["physics", "after"]
    assert [e.text for e in physics.findall("scheme")] == ["a"]
    loop = physics.find("subcycle")
    assert loop.get("loop") == "number_of_subcycles"
    assert [e.text for e in loop.findall("scheme")] == ["c", "b"]
    assert [e.text for e in after.findall("scheme")] == ["c"]


def test_written_xml_reads_back_as_the_same_suite(tmp_path):
    suite = _suite_file(tmp_path)
    (tmp_path / "xml").mkdir()
    (tmp_path / "schemes").mkdir()
    for name in "abc":
        (tmp_path / "schemes" / f"{name}.meta").write_text(_META.format(name=name))
    assert main([str(suite), "-o", str(tmp_path / "xml")]) == 0
    out = io.StringIO()
    assert verify([str(tmp_path / "py")], [str(tmp_path / "xml")],
                  [str(tmp_path / "schemes")], out=out), out.getvalue()
    assert out.getvalue().strip() == "demo: PASS"


def test_call_site_overrides_are_rejected(tmp_path):
    suite = _suite_file(tmp_path, _SUITE.replace("        c()\n\nif", "        c(x=1)\n\nif"))
    with pytest.raises(ValueError, match="call-site argument overrides"):
        py_to_sdf(str(suite))
