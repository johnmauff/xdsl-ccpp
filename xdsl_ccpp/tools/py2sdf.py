"""py2sdf -- write a Python suite as a CCPP suite definition file (XML).

The Python suite is run, its composites (categories, parameterizations,
packages and their hooks) are flattened as the generator does
(``FlattenComposites``), and the resulting groups, schemes and loops are
written as ``<suite>``/``<group>``/``<scheme>``/``<subcycle>``.  The XML
defines the same physics, so it can be given to any CCPP generator,
including ones that only read XML.  The Python structure itself does not
carry over: the file is the flat scheme list.

Scheme metadata is not needed: Python suites name their schemes only.

Usage::

    python -m xdsl_ccpp.tools.py2sdf suites-py/suite_cam4.py \\
        --import-path suites-py --legacy-mode -o suite_cam4.xml

Several suites can be given; ``-o`` is then a directory, and each suite is
written as ``suite_<name>.xml``.  Without ``-o`` the XML goes to stdout.
"""

from __future__ import annotations

import argparse
import os
import sys
import xml.etree.ElementTree as ET

from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.tools.ccpp_dsl import ccppMain
from xdsl_ccpp.tools.ctx_utils import make_ccpp_context
from xdsl_ccpp.transforms.flatten_composites import FlattenComposites
from xdsl_ccpp.util.ccpp_conventions import set_legacy_mode


def add_import_path(paths) -> None:
    """Put *paths* first on ``PYTHONPATH``: a Python suite runs in a
    subprocess and imports the modules it is built from (e.g. suites-py)."""
    if paths:
        os.environ["PYTHONPATH"] = os.pathsep.join(
            [os.path.abspath(p) for p in paths]
            + ([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else []))


def build_module(scheme_files: list[str], legacy_mode: bool, **source):
    """The IR real generation starts from, with composites flattened, for an
    XML suite (``suites=[...]``) or a Python one (``py=...``)."""
    set_legacy_mode(legacy_mode)  # read by the .meta parser (ccppMain.run sets it too)
    tool = ccppMain()
    options_db = tool.default_options_db()
    options_db.update({"suites": [], "scheme_files": scheme_files, "host_files": [],
                       "legacy_mode": legacy_mode, "verbose": 0, **source})
    tool.options_db = tool._normalize_options_db(dict(options_db))
    module = tool._build_cheap_metadata_module()
    FlattenComposites().apply(make_ccpp_context(), module)
    return module


def _add_items(parent: ET.Element, block, where: str) -> None:
    for op in block.ops:
        if isa(op, ccpp.SchemeOp):
            if op.arg_overrides is not None and op.arg_overrides.data:
                raise ValueError(
                    f"{where}: scheme '{op.scheme_name.data}' has call-site argument "
                    f"overrides, which a suite definition file cannot express.")
            ET.SubElement(parent, "scheme").text = op.scheme_name.data
        elif isa(op, ccpp.SubcycleOp):
            loop = ET.SubElement(parent, "subcycle", loop=op.loop_count.data)
            _add_items(loop, op.body.block, where)


def suite_xml(suite: ccpp.SuiteOp) -> str:
    """One flattened suite as suite-definition-file text."""
    attrs = {"name": suite.suite_name.data}
    if suite.version is not None:
        attrs["version"] = suite.version.data
    root = ET.Element("suite", attrs)
    if suite.init_scheme is not None:
        ET.SubElement(root, "init").text = suite.init_scheme.data
    if suite.final_scheme is not None:
        ET.SubElement(root, "final").text = suite.final_scheme.data
    for group in suite.body.block.ops:
        if isa(group, ccpp.GroupOp):
            element = ET.SubElement(root, "group", name=group.group_name.data)
            _add_items(element, group.body.block,
                       f"suite '{suite.suite_name.data}', group '{group.group_name.data}'")
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n\n' + ET.tostring(root, encoding="unicode") + "\n"


def py_to_sdf(py_path: str, legacy_mode: bool = False) -> dict[str, str]:
    """Suite name -> suite-definition-file text, for every suite *py_path*
    defines."""
    module = build_module([], legacy_mode, py=py_path)
    return {s.suite_name.data: suite_xml(s)
            for s in module.body.block.ops if isa(s, ccpp.SuiteOp)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("suites", nargs="+", help="Python suite files")
    parser.add_argument("-o", "--output",
                        help="output file (one suite) or directory; default: stdout")
    parser.add_argument("--import-path", nargs="*", default=[],
                        help="directories the suites import modules from")
    parser.add_argument("--legacy-mode", action="store_true")
    args = parser.parse_args(argv)
    add_import_path(args.import_path)

    written = {}
    for py_path in args.suites:
        try:
            written.update(py_to_sdf(py_path, args.legacy_mode))
        except Exception as exc:
            print(f"py2sdf: {py_path}: {exc}", file=sys.stderr)
            return 1
    if args.output is None:
        sys.stdout.write("".join(written.values()))
    elif len(written) == 1 and not os.path.isdir(args.output):
        with open(args.output, "w") as f:
            f.write(next(iter(written.values())))
    else:
        os.makedirs(args.output, exist_ok=True)
        for name, text in written.items():
            with open(os.path.join(args.output, f"suite_{name}.xml"), "w") as f:
                f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
