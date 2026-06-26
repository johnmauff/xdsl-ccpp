"""Generate datatable.xml and optional HTML documentation from CCPP MLIR.

The datatable records:
  ccpp_files        — the .F90 cap files written by ccpp_xdsl
  schemes           — scheme names and their lifecycle entry points
  api               — suite → group → scheme call structure from the suite XML
  var_dictionaries  — full variable metadata per argument-table entry point

Can be used as a library (build_datatable, write_html) or run as a standalone
CLI via the ``ccpp_datatable`` entry point.

CLI usage::

    ccpp_datatable --mlir ccpp.mlir --caps-dir caps/ -o datatable.xml
    ccpp_datatable --mlir ccpp.mlir --caps-dir caps/ -o datatable.xml --html-dir docs/
"""
from __future__ import annotations

import argparse
import html as html_mod
import os
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.dom import minidom

from xdsl.context import Context
from xdsl.dialects import builtin
from xdsl.parser import Parser
from xdsl.universe import Universe
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp import (
    CCPP,
    ArgumentOp,
    ArgumentTableOp,
    GroupOp,
    SchemeOp,
    SubcycleOp,
    SuiteOp,
    TablePropertiesOp,
)
from xdsl_ccpp.dialects.ccpp_utils import CCPPUtils


# ── MLIR context ──────────────────────────────────────────────────────────────

def _make_ctx() -> Context:
    ctx = Context()
    for name, factory in Universe.get_multiverse().all_dialects.items():
        ctx.register_dialect(name, factory)
    ctx.load_dialect(CCPP)
    ctx.load_dialect(CCPPUtils)
    return ctx


# ── IR walkers ────────────────────────────────────────────────────────────────

def _get_string(attr) -> str:
    """Return the string data of a StringAttr, or '' if None."""
    return attr.data if attr is not None else ""


def _get_int(attr) -> int:
    """Return the integer data of an IntAttr, or 0 if None."""
    return attr.data if attr is not None else 0


def _iter_schemes_in_group(group_op):
    """Yield SchemeOp names (str) from a GroupOp body, descending into SubcycleOp."""
    for op in group_op.body.block.ops:
        if isa(op, SchemeOp):
            yield op.scheme_name.data
        elif isa(op, SubcycleOp):
            for inner in op.body.block.ops:
                if isa(inner, SchemeOp):
                    yield inner.scheme_name.data


def _collect_suites(ccpp_mod):
    """Return list of SuiteOp from the @ccpp named module."""
    suites = []
    for op in ccpp_mod.body.block.ops:
        if isa(op, SuiteOp):
            suites.append(op)
    return suites


def _collect_table_properties(ccpp_mod):
    """Return list of (TablePropertiesOp, [ArgumentTableOp]) from @ccpp module."""
    result = []
    for op in ccpp_mod.body.block.ops:
        if not isa(op, TablePropertiesOp):
            continue
        arg_tables = []
        for child in op.body.block.ops:
            if isa(child, ArgumentTableOp):
                arg_tables.append(child)
        result.append((op, arg_tables))
    return result


def _arg_op_to_dict(arg_op: ArgumentOp) -> dict:
    """Extract all available properties from an ArgumentOp into a plain dict."""
    dims_count = _get_int(arg_op.dimensions)
    dim_names_raw = _get_string(arg_op.dim_names)
    if dims_count == 0:
        dimensions_str = "()"
    else:
        dim_names = [d.strip() for d in dim_names_raw.split(",") if d.strip()]
        dimensions_str = "(" + ", ".join(dim_names) + ")"

    return {
        "local_name":    _get_string(arg_op.arg_name),
        "standard_name": _get_string(arg_op.standard_name),
        "long_name":     _get_string(arg_op.long_name),
        "units":         _get_string(arg_op.units),
        "type":          _get_string(arg_op.arg_type),
        "dimensions":    dimensions_str,
        "kind":          _get_string(arg_op.kind),
        "intent":        _get_string(arg_op.intent),
    }


# ── Entry-point phase detection ───────────────────────────────────────────────

_PHASE_SUFFIXES = (
    ("_run",               "run"),
    ("_init",              "init"),
    ("_finalize",          "finalize"),
    ("_timestep_final",    "timestep_final"),
    ("_timestep_init",     "timestep_init"),
)


def _phase_for_entry(entry_name: str, scheme_name: str) -> str:
    """Return the lifecycle phase label for an entry point name."""
    lower = entry_name.lower()
    for suffix, label in _PHASE_SUFFIXES:
        if lower.endswith(suffix):
            return label
    # fallback: strip the scheme_name prefix
    if lower.startswith(scheme_name.lower() + "_"):
        return lower[len(scheme_name) + 1:]
    return "unknown"


# ── Top-level build function ──────────────────────────────────────────────────

def build_datatable(mlir_text: str, cap_files: list[str], host_name: str = "") -> ET.Element:
    """Build an ``ElementTree`` element tree representing the datatable.

    Args:
        mlir_text: The frontend MLIR text (before optimization passes).
        cap_files: Absolute or relative paths to the generated ``.F90`` files.
        host_name: Optional host model name written into the root element.

    Returns:
        An ``xml.etree.ElementTree.Element`` for the ``<datatable>`` root.
    """
    ctx = _make_ctx()
    module = Parser(ctx, mlir_text).parse_op()

    # Locate the @ccpp named sub-module
    ccpp_mod = None
    for child in module.body.block.ops:
        if isa(child, builtin.ModuleOp):
            sym = child.sym_name
            if sym is not None and sym.data == "ccpp":
                ccpp_mod = child
                break
    if ccpp_mod is None:
        # Try a bare module (some test fixtures omit the named wrapper)
        ccpp_mod = module

    root = ET.Element("datatable")
    if host_name:
        root.set("host_name", host_name)

    # ── ccpp_files ────────────────────────────────────────────────────────────
    files_el = ET.SubElement(root, "ccpp_files")
    for cap in sorted(cap_files):
        f_el = ET.SubElement(files_el, "file")
        f_el.set("path", str(cap))

    # ── schemes (entry-point metadata) ────────────────────────────────────────
    schemes_el = ET.SubElement(root, "schemes")
    table_props = _collect_table_properties(ccpp_mod)
    scheme_names_seen: set[str] = set()
    for tbl_op, arg_tables in table_props:
        if tbl_op.table_type.data != "scheme":
            continue
        scheme_name = tbl_op.table_name.data
        if scheme_name in scheme_names_seen:
            continue
        scheme_names_seen.add(scheme_name)
        s_el = ET.SubElement(schemes_el, "scheme")
        s_el.set("name", scheme_name)
        for at in arg_tables:
            ep_el = ET.SubElement(s_el, "entry_point")
            ep_el.set("name", at.table_name.data)
            ep_el.set("phase", _phase_for_entry(at.table_name.data, scheme_name))

    # ── api (suite call structure) ────────────────────────────────────────────
    api_el = ET.SubElement(root, "api")
    for suite_op in _collect_suites(ccpp_mod):
        suite_el = ET.SubElement(api_el, "suite")
        suite_el.set("name", suite_op.suite_name.data)
        if suite_op.version is not None:
            suite_el.set("version", suite_op.version.data)
        for op in suite_op.body.block.ops:
            if not isa(op, GroupOp):
                continue
            grp_el = ET.SubElement(suite_el, "group")
            grp_el.set("name", op.group_name.data)
            for scheme_name in _iter_schemes_in_group(op):
                sc_el = ET.SubElement(grp_el, "scheme")
                sc_el.set("name", scheme_name)

    # ── var_dictionaries (full variable metadata per entry point) ─────────────
    vd_el = ET.SubElement(root, "var_dictionaries")
    for tbl_op, arg_tables in table_props:
        for at in arg_tables:
            dict_el = ET.SubElement(vd_el, "var_dictionary")
            dict_el.set("source", at.table_name.data)
            dict_el.set("table_type", tbl_op.table_type.data)
            for arg_op in at.body.block.ops:
                if not isa(arg_op, ArgumentOp):
                    continue
                info = _arg_op_to_dict(arg_op)
                var_el = ET.SubElement(dict_el, "variable")
                for key, val in info.items():
                    var_el.set(key, val)

    return root


def write_datatable(root_el: ET.Element, output_path: str) -> None:
    """Pretty-print the datatable XML element to *output_path*."""
    raw = ET.tostring(root_el, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    # minidom adds an XML declaration; keep it
    lines = [ln for ln in pretty.splitlines() if ln.strip()]
    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")


# ── HTML generation ───────────────────────────────────────────────────────────

_HTML_COLUMNS = [
    ("local_name",    "Local name"),
    ("standard_name", "Standard name"),
    ("long_name",     "Long name"),
    ("units",         "Units"),
    ("type",          "Type"),
    ("dimensions",    "Dimensions"),
    ("kind",          "Kind"),
    ("intent",        "Intent"),
]

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{ font-family: sans-serif; font-size: 14px; margin: 2em; }}
  h1 {{ font-size: 1.4em; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
  th {{ background: #f0f0f0; font-weight: bold; }}
  tr:nth-child(even) {{ background: #fafafa; }}
</style>
</head>
<body>
<h1>{title}</h1>
<table>
<thead>
<tr>{header_cells}</tr>
</thead>
<tbody>
{rows}
</tbody>
</table>
</body>
</html>
"""


def write_html(root_el: ET.Element, html_dir: str) -> list[str]:
    """Write one HTML file per var_dictionary entry into *html_dir*.

    Returns the list of written file paths.
    """
    os.makedirs(html_dir, exist_ok=True)
    written: list[str] = []

    header_cells = "".join(f"<th>{col_label}</th>" for _, col_label in _HTML_COLUMNS)

    for dict_el in root_el.findall("./var_dictionaries/var_dictionary"):
        source = dict_el.get("source", "unknown")
        rows_html = []
        for var_el in dict_el.findall("variable"):
            cells = "".join(
                f"<td>{html_mod.escape(var_el.get(col_key, ''))}</td>"
                for col_key, _ in _HTML_COLUMNS
            )
            rows_html.append(f"<tr>{cells}</tr>")

        if not rows_html:
            continue

        title = html_mod.escape(source)
        page = _HTML_TEMPLATE.format(
            title=title,
            header_cells=header_cells,
            rows="\n".join(rows_html),
        )
        out_path = os.path.join(html_dir, f"{source}.html")
        with open(out_path, "w") as f:
            f.write(page)
        written.append(out_path)

    return written


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate datatable.xml (and optionally HTML docs) from CCPP MLIR."
    )
    parser.add_argument(
        "--mlir",
        required=True,
        metavar="FILE",
        help="Frontend MLIR file (ccpp.mlir produced by ccpp_xdsl before optimization).",
    )
    parser.add_argument(
        "--caps-dir",
        required=True,
        metavar="DIR",
        help="Directory containing the generated .F90 cap files.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="datatable.xml",
        metavar="FILE",
        help="Output path for datatable.xml (default: datatable.xml).",
    )
    parser.add_argument(
        "--html-dir",
        default=None,
        metavar="DIR",
        help="If set, write one HTML variable table per entry point into this directory.",
    )
    parser.add_argument(
        "--host-name",
        default="",
        metavar="NAME",
        help="Host model name written into the datatable root element.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)

    if not os.path.isfile(args.mlir):
        print(f"Error: MLIR file not found: '{args.mlir}'", file=sys.stderr)
        sys.exit(1)
    if not os.path.isdir(args.caps_dir):
        print(f"Error: caps directory not found: '{args.caps_dir}'", file=sys.stderr)
        sys.exit(1)

    with open(args.mlir) as f:
        mlir_text = f.read()

    cap_files = [
        str(p) for p in Path(args.caps_dir).glob("*.F90")
    ]

    root_el = build_datatable(mlir_text, cap_files, host_name=args.host_name)
    write_datatable(root_el, args.output)
    print(f"Wrote datatable: {args.output}")

    if args.html_dir:
        written = write_html(root_el, args.html_dir)
        for path in written:
            print(f"  -> Wrote HTML: {path}")


if __name__ == "__main__":
    main()
