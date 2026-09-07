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

from xdsl.dialects import builtin
from xdsl.parser import Parser
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp import (
    ArgumentOp,
    ArgumentTableOp,
    GroupOp,
    SchemeOp,
    SubcycleOp,
    SuiteOp,
    TablePropertiesOp,
)
from xdsl_ccpp.tools.ctx_utils import make_ccpp_context


# ── Framework-shipped Fortran support files (task #75) ─────────────────────────
#
# Modeled directly on real capgen-v1's own
# ccpp_capgen.py:_FRAMEWORK_SRC_DIR/_FRAMEWORK_F90_FILES/
# _resolve_framework_f90_files() -- these files must live inside the
# installed xdsl_ccpp package itself (not examples/shared/, which only ever
# existed in this repo's own checkout and is unreachable from an installed
# package or a real host model like CAM-SIMA), the same way capgen-v1 ships
# its own copies under capgen/src/ rather than expecting a host to supply
# them.
_FRAMEWORK_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "framework_src")
_FRAMEWORK_F90_FILES = (
    "ccpp_constituent_prop_mod.F90",
    "ccpp_scheme_utils.F90",
)

# Real CCPP framework files needed when cam_host=True (in compile order so
# ccpp_hashable is ready before ccpp_hash_table, and both before
# ccpp_constituent_prop_mod which depends on them).
_REAL_FRAMEWORK_F90_FILES = (
    "ccpp_hashable.F90",
    "ccpp_hash_table.F90",
    "ccpp_constituent_prop_mod.F90",
    "ccpp_scheme_utils.F90",
)


def _resolve_framework_f90_files() -> list[str]:
    """Return absolute paths for xdsl_ccpp's own framework F90 files.

    Each name in `_FRAMEWORK_F90_FILES` is looked up under
    `_FRAMEWORK_SRC_DIR` (`xdsl_ccpp/framework_src/`). A missing file is a
    hard error, not a silent skip -- `_FRAMEWORK_SRC_DIR` is the canonical
    (and only) location, and a missing file here means the installed
    package is incomplete; surfacing that now with a precise message beats
    letting a host build fail later with an opaque "Cannot open module
    file" error once it tries to compile against a `<utilities>` list
    entry that was never actually there.
    """
    found: list[str] = []
    missing: list[str] = []
    for name in _FRAMEWORK_F90_FILES:
        path = os.path.join(_FRAMEWORK_SRC_DIR, name)
        if os.path.isfile(path):
            found.append(os.path.abspath(path))
        else:
            missing.append(path)
    if missing:
        raise FileNotFoundError(
            "xdsl_ccpp installation is incomplete: required framework "
            f"Fortran source file(s) not found under {_FRAMEWORK_SRC_DIR!r}:\n  "
            + "\n  ".join(missing)
        )
    return found


# ── IR walkers ────────────────────────────────────────────────────────────────

def _get_string(attr) -> str:
    """Return the string data of a StringAttr, or '' if None."""
    return attr.data if attr is not None else ""


def _get_int(attr) -> int:
    """Return the integer data of an IntAttr, or 0 if None."""
    return attr.data if attr is not None else 0


def _iter_schemes_in_group(group_op):
    """Yield SchemeOp names (str) from a GroupOp (or SubcycleOp) body,
    descending recursively into arbitrarily-nested SubcycleOp.

    A single level of SubcycleOp descent isn't enough -- real suites nest
    subcycles several levels deep (e.g.
    examples/var_compat/var_compatibility_suite.xml:5-11 nests three
    levels in one branch), and this function backs `_used_scheme_names()`
    (capgen_v1_parity_backlog.md Stage 8b's dependency-reference filter),
    where under-counting used schemes means silently dropping a real
    dependency a host build needs to compile against, not just an
    incomplete `<api>` section entry (flagged by Copilot review, PR #94).
    GroupOp and SubcycleOp share the same `body = region_def("single_block")`
    shape, so recursing into a SubcycleOp via this same function works
    unchanged.
    """
    for op in group_op.body.block.ops:
        if isa(op, SchemeOp):
            yield op.scheme_name.data
        elif isa(op, SubcycleOp):
            yield from _iter_schemes_in_group(op)


def _collect_suites(ccpp_mod):
    """Return list of SuiteOp from the @ccpp named module."""
    suites = []
    for op in ccpp_mod.body.block.ops:
        if isa(op, SuiteOp):
            suites.append(op)
    return suites


def _used_scheme_names(ccpp_mod) -> set[str]:
    """Return the set of scheme names actually referenced by some suite --
    either via group membership (including arbitrarily-nested subcycles)
    or the suite's own `init_scheme`/`final_scheme` (v2.0 SDF schema, see
    `SuiteOp`'s own docstring) -- mirrors real capgen-v1's own
    `used_scheme_names` gate in `ccpp_capgen.py` exactly (that gate adds
    `suite_init_call`/`suite_final_call`'s own scheme name alongside every
    group-phase call): host/DDT tables' dependencies always contribute;
    a scheme table's own dependencies only contribute if the scheme is
    actually referenced by a resolved suite, since an unreferenced scheme
    passed on the CLI for build-system convenience shouldn't leak its
    dependencies (capgen_v1_parity_backlog.md Stage 8b).

    Originally missed both the arbitrary-nesting case and this
    init_scheme/final_scheme case (Copilot review, PR #94, confirmed
    correct against examples/var_compat/var_compatibility_suite.xml's own
    three-level subcycle nesting) -- fixed by delegating the nesting fix to
    `_iter_schemes_in_group` itself and adding both suite-level properties
    here.
    """
    used: set[str] = set()
    for suite_op in _collect_suites(ccpp_mod):
        if suite_op.init_scheme is not None:
            used.add(suite_op.init_scheme.data)
        if suite_op.final_scheme is not None:
            used.add(suite_op.final_scheme.data)
        for op in suite_op.body.block.ops:
            if isa(op, GroupOp):
                used.update(_iter_schemes_in_group(op))
    return used


def _collect_dependencies(ccpp_mod, table_props) -> list[str]:
    """Return the deduped, sorted list of dependency file paths
    (capgen_v1_parity_backlog.md Stage 8b) -- real capgen-v1's own
    `<dependencies>` section, sourced from each table's own
    `dependencies`/`dependencies_path` metadata (task #6 Tier 1's already-
    IR-forwarded attributes).

    Filtering mirrors real capgen-v1's own `ccpp_capgen.py` gate: HOST-,
    MODULE-, and DDT-type tables always contribute (approximating real
    capgen-v1's own "DDT/host Fortran is shared across suites" rule,
    without that tool's finer-grained "DDT co-located with a *used*
    scheme's own .meta file" distinction -- xdsl_ccpp's IR doesn't carry
    which .meta file a table came from, so this always-include is a
    deliberate, safe over-inclusion rather than a fragile approximation of
    that narrower rule); SCHEME-type tables only contribute if the scheme
    is in `_used_scheme_names`.

    Known limitation, not solved here: each dependency is joined with its
    own table's `dependencies_path` (when set) via a plain relative
    `os.path.join` -- real capgen-v1's own convention resolves
    `dependencies_path` relative to the *original .meta file's own
    directory*, but that directory isn't available at this layer
    (`build_datatable` receives parsed MLIR text and a cap-files list, not
    the original --scheme-files/--host-files search paths -- see
    ccpp_dsl.py:697's own call site). Callers needing an absolute path
    must resolve this relative path against their own known scheme/host
    search directory; this is a real, deliberate gap, not an oversight.
    """
    used_schemes = _used_scheme_names(ccpp_mod)
    deps: set[str] = set()
    for tbl_op, _arg_tables in table_props:
        table_type = tbl_op.table_type.data
        if table_type == "scheme" and tbl_op.table_name.data not in used_schemes:
            continue
        # Plain xDSL `.attributes` dict access, not a hasAttr/getAttr
        # convenience method -- TablePropertiesOp (unlike the descriptor-
        # layer CCPPArgument objects elsewhere in this codebase) doesn't
        # define those. Matches suite_kinds.py's own
        # `table_prop_op.attributes.get("kind_specs")` precedent for
        # reading an optional TablePropertiesOp attribute directly.
        deps_attr = tbl_op.attributes.get("dependencies")
        if deps_attr is None:
            continue
        dep_dir_attr = tbl_op.attributes.get("dependencies_path")
        dep_dir = dep_dir_attr.data if dep_dir_attr is not None else None
        for dep_name_attr in deps_attr.data:
            dep_name = dep_name_attr.data
            deps.add(os.path.join(dep_dir, dep_name) if dep_dir else dep_name)
    return sorted(deps)


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

def build_datatable(
    mlir_text: str,
    cap_files: list[str],
    host_name: str = "",
    cam_host: bool = False,
    framework_src_dir: str = "",
) -> ET.Element:
    """Build an ``ElementTree`` element tree representing the datatable.

    Args:
        mlir_text: The frontend MLIR text (before optimization passes).
        cap_files: Absolute or relative paths to the generated ``.F90`` files.
        host_name: Optional host model name written into the root element.
        cam_host: When True, replace the bundled framework F90 stub files with
            real ccpp_framework source files from ``framework_src_dir``.
        framework_src_dir: Path to the real ccpp_framework/src directory.
            Required when cam_host=True; ignored otherwise.

    Returns:
        An ``xml.etree.ElementTree.Element`` for the ``<datatable>`` root.
    """
    ctx = make_ccpp_context()
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

    # Utility files: ccpp_kinds.F90 (generated, if present) + bundled
    # framework F90 files. Collected once and written into both <ccpp_files>
    # and <capgen_files> because xdsl_ccpp's cmake reader uses <ccpp_files>
    # while capgen-v1's ccpp_datafile.py DatatableReport("utility_files")
    # reads from <capgen_files>.
    utility_file_texts: list[str] = []
    for cap in sorted(cap_files):
        if os.path.basename(str(cap)) == "ccpp_kinds.F90":
            utility_file_texts.append(str(cap))
    if cam_host:
        if framework_src_dir:
            for name in _REAL_FRAMEWORK_F90_FILES:
                path = os.path.join(framework_src_dir, name)
                if not os.path.isfile(path):
                    raise FileNotFoundError(
                        f"cam_host=True: real framework file not found: {path!r}\n"
                        f"  (framework_src_dir={framework_src_dir!r})"
                    )
                utility_file_texts.append(os.path.abspath(path))
    else:
        for framework_file in _resolve_framework_f90_files():
            utility_file_texts.append(framework_file)

    # ── ccpp_files ────────────────────────────────────────────────────────────
    # Cap files are listed as <file path="..."/> for cmake/parse_xdsl_ccpp_
    # datatable.py (which reads them for the Fortran build step).
    # parse_xdsl_ccpp_datatable.py skips non-<file path="..."> children to
    # avoid tripping on the subcategory elements.
    files_el = ET.SubElement(root, "ccpp_files")
    for cap in sorted(cap_files):
        f_el = ET.SubElement(files_el, "file")
        f_el.set("path", str(cap))
    utilities_el = ET.SubElement(files_el, "utilities")
    for u_text in utility_file_texts:
        u_el = ET.SubElement(utilities_el, "file")
        u_el.text = u_text
    ET.SubElement(files_el, "host_files")
    ET.SubElement(files_el, "suite_files")

    # ── capgen_files ──────────────────────────────────────────────────────────
    # capgen-v1's ccpp_datafile.py reads utility_files from this section.
    capgen_files_el = ET.SubElement(root, "capgen_files")
    capgen_utilities_el = ET.SubElement(capgen_files_el, "utilities")
    for u_text in utility_file_texts:
        u_el = ET.SubElement(capgen_utilities_el, "file")
        u_el.text = u_text
    ET.SubElement(capgen_files_el, "host_files")
    ET.SubElement(capgen_files_el, "suite_files")

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

    # ── dependencies (capgen_v1_parity_backlog.md Stage 8b) ───────────────────
    # A top-level sibling of ccpp_files/schemes/api/var_dictionaries above,
    # not nested inside any of them -- matches real capgen-v1's own
    # <ccpp_datatable><dependencies><dependency>path</dependency>...</
    # dependencies></ccpp_datatable> shape exactly (confirmed against
    # ccpp-framework-fresh/capgen/generator/datatable.py:487-490), letting
    # real capgen-v1's own vendored ccpp_datafile.py read this file's
    # DatatableReport("dependencies") query unchanged -- ccpp_datafile.py's
    # own readers never validate the root element's tag name, only look up
    # direct children by tag, so this file's own <datatable> root (vs. real
    # capgen-v1's <ccpp_datatable>) doesn't need to change for this to work.
    deps_el = ET.SubElement(root, "dependencies")
    for dep_path in _collect_dependencies(ccpp_mod, table_props):
        d_el = ET.SubElement(deps_el, "dependency")
        d_el.text = dep_path

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
