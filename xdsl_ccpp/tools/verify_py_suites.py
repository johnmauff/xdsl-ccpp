"""verify_py_suites -- check that Python suites define the same physics as
their XML suites.

For every ``suite_<name>.py`` in the ``--py-dir`` directories that has a
``suite_<name>.xml`` in an ``--xml-dir`` directory, both are built into the
IR real generation starts from (``ccppMain._build_cheap_metadata_module``,
with the ``.meta`` files of the schemes the XML suite calls), the Python
form's composites are flattened (``FlattenComposites``), and the two are
compared:

- PASS: identical IR;
- PASS (moved init-only schemes): identical except for the position of
  schemes that only have register/init/final phases -- they run once, so
  their order does not affect time stepping (``--strict`` makes this a
  failure);
- FAIL: anything else, with the first difference.

``--case CASE_DIR ...`` also generates the caps of built CAM-SIMA cases from
both forms of their suite (with the case's host metadata) and compares them
file by file: identical, or differing only by package-private names
(``<package>__`` prefixes, and their removal from host-visible variable
lists) and, where init-only schemes moved, inside init/register routines.

``--write-xml DIR`` also writes each Python suite's flattened form as a suite
definition file (see ``py2sdf``).

Usage (from a CAM-SIMA checkout's ``src/physics/ncar_ccpp``)::

    python -m xdsl_ccpp.tools.verify_py_suites \\
        --py-dir suites-py test/test_suites-py --xml-dir suites test/test_suites \\
        --scheme-dir schemes test/test_schemes --import-path suites-py --legacy-mode

Exit status 1 if any suite fails.
"""

from __future__ import annotations

import argparse
import difflib
import glob
import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter

from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.tools.ccpp_dsl import ccppMain
from xdsl_ccpp.tools.py2sdf import add_import_path, build_module, suite_xml
from xdsl_ccpp.transforms.util.cap_shared import split_scheme_table_name

# Phases a scheme runs in once per run; moving such a scheme does not change
# the order of anything done per time step.
_ONCE_PHASES = {"register", "initialize", "finalize"}


def scheme_meta_index(scheme_dirs: list[str]) -> dict[str, str]:
    """Scheme name -> ``.meta`` file, searching *scheme_dirs* recursively in
    order; the first file declaring a scheme wins (as in CAM's
    ``cam_autogen``)."""
    index: dict[str, str] = {}
    for sdir in scheme_dirs:
        for path in sorted(glob.glob(os.path.join(sdir, "**", "*.meta"), recursive=True)):
            text = open(path, encoding="utf-8", errors="replace").read()
            for block in text.split("[ccpp-table-properties]")[1:]:
                header = block.split("[ccpp-arg-table]")[0]
                name = re.search(r"^\s*name\s*=\s*(\S+)", header, re.M)
                kind = re.search(r"^\s*type\s*=\s*(\S+)", header, re.M)
                if name and kind and kind.group(1).lower() == "scheme":
                    index.setdefault(name.group(1), path)
    return index


def xml_scheme_names(xml_path: str) -> list[str]:
    """Names of the schemes an XML suite calls."""
    return [e.text.strip() for e in ET.parse(xml_path).getroot().iter("scheme") if e.text]


def _items(block) -> list:
    """A group's (or loop's) calls, in order: ``("scheme", name, overrides)``
    or ``("loop", count, [items])``."""
    out = []
    for op in block.ops:
        if isa(op, ccpp.SchemeOp):
            overrides = (tuple(sorted((k, str(v)) for k, v in op.arg_overrides.data.items()))
                         if op.arg_overrides is not None else ())
            out.append(("scheme", op.scheme_name.data, overrides))
        elif isa(op, ccpp.SubcycleOp):
            out.append(("loop", op.loop_count.data, _items(op.body.block)))
    return out


def suite_structure(module) -> dict:
    """Suite name -> [(group name, items)]."""
    return {
        suite.suite_name.data: [(g.group_name.data, _items(g.body.block))
                                for g in suite.body.block.ops if isa(g, ccpp.GroupOp)]
        for suite in module.body.block.ops if isa(suite, ccpp.SuiteOp)
    }


def once_only_schemes(module) -> set:
    """Schemes whose argument tables are all run-once phases."""
    phases: dict[str, set] = {}
    for props in module.body.block.ops:
        if not isa(props, ccpp.TablePropertiesOp):
            continue
        for table in props.body.block.ops:
            if isa(table, ccpp.ArgumentTableOp):
                split = split_scheme_table_name(table.table_name.data)
                if split is not None:
                    phases.setdefault(split[0], set()).add(split[1])
    return {s for s, p in phases.items() if p and p <= _ONCE_PHASES}


def _without(items, names) -> tuple[list, list]:
    """*items* without schemes in *names*, and the removed scheme names."""
    kept, removed = [], []
    for item in items:
        if item[0] == "scheme" and item[1] in names:
            removed.append(item[1])
        elif item[0] == "loop":
            inner, gone = _without(item[2], names)
            kept.append(("loop", item[1], inner))
            removed.extend(gone)
        else:
            kept.append(item)
    return kept, removed


def _first_difference(a: list, b: list) -> str:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return f"item {i}: XML {x[:2]} vs Python {y[:2]}"
    return f"lengths: XML {len(a)} vs Python {len(b)}"


def _placements(groups, once) -> Counter:
    """Where each run-once scheme sits: (scheme, group, number of other
    schemes before it in the group)."""
    placed = Counter()

    def walk(items, group, before):
        for item in items:
            if item[0] == "loop":
                before = walk(item[2], group, before)
            elif item[1] in once:
                placed[(item[1], group, before)] += 1
            else:
                before += 1
        return before

    for group, items in groups:
        walk(items, group, 0)
    return placed


def compare(xml_module, py_module, strict: bool = False) -> tuple[str, list[str], list[str]]:
    """``("PASS"|"FAIL", details, moved init-only schemes)`` for one suite's
    two flattened forms."""
    status, details = _compare(xml_module, py_module)
    moved = details.pop() if status == "MOVED" else []
    if status != "MOVED":
        return status, details, moved
    note = f"moved init-only schemes: {', '.join(moved)}"
    return ("FAIL", [note + " (--strict)"], moved) if strict else ("PASS", [note], moved)


def _compare(xml_module, py_module) -> tuple[str, list]:
    if str(xml_module) == str(py_module):
        return "PASS", []
    tables = lambda m: sorted(str(op) for op in m.body.block.ops if not isa(op, ccpp.SuiteOp))
    if tables(xml_module) != tables(py_module):
        return "FAIL", ["scheme metadata differs"]
    xs, ps = suite_structure(xml_module), suite_structure(py_module)
    if list(xs) != list(ps):
        return "FAIL", [f"suites: XML {list(xs)} vs Python {list(ps)}"]
    once = once_only_schemes(xml_module)
    details, moved = [], []
    for name in xs:
        xg, pg = xs[name], ps[name]
        if [g for g, _ in xg] != [g for g, _ in pg]:
            return "FAIL", [f"{name}: groups XML {[g for g, _ in xg]} vs Python {[g for g, _ in pg]}"]
        x_once, p_once = Counter(), Counter()
        for (group, xi), (_, pi) in zip(xg, pg):
            xk, xr = _without(xi, once)
            pk, pr = _without(pi, once)
            x_once.update(xr)
            p_once.update(pr)
            if xk != pk:
                details.append(f"{name}/{group}: {_first_difference(xk, pk)}")
        if x_once != p_once:
            details.append(f"{name}: run-once schemes differ: XML {sorted(x_once.elements())} "
                           f"vs Python {sorted(p_once.elements())}")
        xp, pp = _placements(xg, once), _placements(pg, once)
        moved += sorted({key[0] for key in (xp - pp) + (pp - xp)})
    if details:
        return "FAIL", details
    if not moved:
        return "FAIL", ["IR differs outside the suites' groups"]
    return "MOVED", [list(dict.fromkeys(moved))]


def _case_options(case_dir: str) -> tuple[str, dict]:
    """(suite name, generator options) a built CAM-SIMA case generated its
    caps with, from its build cache (host metadata, scheme files, GPU)."""
    exeroot = os.path.join(case_dir, "bld")
    cache = ET.parse(os.path.join(exeroot, "atm", "obj", "cam_build_cache.xml")).getroot()
    paths = lambda tag: [e.get("file_path") for e in cache.iter(tag) if e.get("file_path")]
    sdf = os.path.basename(paths("SDF")[0])
    suite = sdf[len("suite_"):].rsplit(".", 1)[0]
    env = open(os.path.join(case_dir, "env_build.xml")).read()
    srcroot = re.search(r'id="SRCROOT"[^>]*value="([^"]*)"',
                        open(os.path.join(case_dir, "env_case.xml")).read()).group(1)
    options = {"scheme_files": paths("scheme"),
               "host_files": paths("host") + paths("scheme_namelist_meta_file"),
               "host_name": "cam", "cam_host": True, "legacy_mode": True,
               "framework_src_dir": os.path.join(srcroot, "ccpp_framework", "src"),
               "kind_map": ["r8:REAL64"], "verbose": 0}
    if re.search(r'id="OPENACC_GPU_OFFLOAD"[^>]*value="TRUE"', env):
        options["directive"] = "acc"
    return suite, options


def _generate(options: dict, out_dir: str, **source) -> dict[str, list[str]]:
    """Generated file -> lines, for one suite form."""
    tool = ccppMain()
    options_db = tool.default_options_db()
    options_db.update({"suites": [], **options, **source, "out": out_dir,
                       "tempdir": os.path.join(out_dir, "tmp"),
                       "emit_resolved_vars": os.path.join(out_dir, "resolved_vars.json")})
    tool.run(options_db)
    return {f: open(os.path.join(out_dir, f)).read().splitlines()
            for f in sorted(os.listdir(out_dir)) if os.path.isfile(os.path.join(out_dir, f))}


def _routines(lines) -> list[str]:
    """The name of the subroutine each line belongs to ("" outside one)."""
    names, current = [], ""
    for line in lines:
        m = re.match(r"\s*subroutine\s+(\w+)", line, re.I)
        if m:
            current = m.group(1).lower()
        names.append(current)
        if re.match(r"\s*end\s+subroutine", line, re.I):
            current = ""
    return names


def _explained(xml_lines, py_lines, packages, private, moved) -> tuple[bool, set]:
    """Whether every difference between two generated files is one a Python
    suite may make, and which kinds occur:
    - ``package-private names``: ``<package>__`` prefixes (lowercased names);
    - ``private names leave host lists``: Python-only removals of lines naming
      a package-private standard name (and the list's size);
    - ``init routines (moved init-only schemes)``: with moved init-only
      schemes, any difference inside an init/register routine (argument
      order and names come from a routine's first scheme).
    """
    prefix = re.compile(rf"\b(?:{'|'.join(packages)})__(\w+)") if packages else None
    norm_x = [l.lower() for l in xml_lines]
    norm_p = [prefix.sub(r"\1", l).lower() if prefix else l.lower() for l in py_lines]
    kinds = set()
    if norm_p != [l.lower() for l in py_lines]:
        kinds.add("package-private names")
    routines_x, routines_p = _routines(xml_lines), _routines(py_lines)
    once_routine = lambda r: bool(r) and ("init" in r or "register" in r)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, norm_x, norm_p,
                                                       autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if moved and all(once_routine(r) for r in routines_x[i1:i2] + routines_p[j1:j2]):
            kinds.add("init routines (moved init-only schemes)")
            continue
        listed = lambda ls: [re.search(r"scheme_list\(\d+\)\s*=\s*'(\w+)", l) for l in ls]
        x_listed, p_listed = listed(norm_x[i1:i2]), listed(norm_p[j1:j2])
        if (moved and all(x_listed) and all(p_listed)
                and Counter(m.group(1) for m in x_listed) == Counter(m.group(1) for m in p_listed)):
            kinds.add("scheme list order (moved init-only schemes)")
            continue
        removed = norm_x[i1:i2]
        if j1 == j2 and all(any(n in l for n in private) or "var_list(" in l for l in removed):
            kinds.add("private names leave host lists")
            continue
        if tag == "replace" and all("var_list(" in l for l in removed + norm_p[j1:j2]):
            kinds.add("private names leave host lists")
            continue
        return False, kinds
    return True, kinds


def _explained_json(xml_lines, py_lines, packages, moved) -> tuple[bool, set]:
    """resolved_vars.json: the same entries per phase, in the same order --
    except for run-once phases where init-only schemes moved -- once
    ``<package>__`` prefixes are removed (names lowercased)."""
    prefix = re.compile(rf"\b(?:{'|'.join(packages)})__(\w+)") if packages else None
    xml_text, py_text = "\n".join(xml_lines), "\n".join(py_lines)
    py_norm = prefix.sub(r"\1", py_text) if prefix else py_text
    kinds = {"package-private names"} if py_norm != py_text else set()
    x, p = json.loads(xml_text.lower()), json.loads(py_norm.lower())
    if x.get("host_vars") != p.get("host_vars") or set(x["phases"]) != set(p["phases"]):
        return False, kinds
    for phase, entries in x["phases"].items():
        if entries == p["phases"][phase]:
            continue
        # The dummy argument name comes from the routine's first scheme.
        key = lambda e: json.dumps({k: v for k, v in e.items() if k != "arg_name"},
                                   sort_keys=True)
        if moved and phase in _ONCE_PHASES and sorted(map(key, entries)) == sorted(
                map(key, p["phases"][phase])):
            kinds.add(f"{phase} entry order (moved init-only schemes)")
            continue
        return False, kinds
    return True, kinds


def verify_case(case_dir, py_suites, xml_suites, moved_by_suite, out=sys.stdout) -> bool:
    """Generate a built case's caps from its suite's XML and Python forms
    and compare them file by file."""
    name = os.path.basename(case_dir.rstrip("/"))
    suite, options = _case_options(case_dir)
    if suite not in py_suites or suite not in xml_suites:
        print(f"{name}: suite {suite} has no Python and XML pair to compare", file=out)
        return True
    moved = moved_by_suite.get(suite, [])
    with tempfile.TemporaryDirectory() as tmp:
        xml_out = _generate(options, os.path.join(tmp, "xml"), suites=[xml_suites[suite]])
        py_out = _generate(options, os.path.join(tmp, "py"), py=py_suites[suite])
    # Packages, and their private standard names without the prefix, lowercased.
    renamed = re.findall(r'"standard_name":\s*"(\w+?)__(\w+)"',
                         "\n".join(py_out.get("resolved_vars.json", [])))
    packages = sorted({pkg for pkg, _ in renamed})
    private = {name.lower() for _, name in renamed}
    problems, kinds = [], set()
    for f in sorted(set(xml_out) | set(py_out)):
        if f not in xml_out or f not in py_out:
            problems.append(f"{f}: only from the {'XML' if f in xml_out else 'Python'} form")
            continue
        if xml_out[f] == py_out[f]:
            continue
        if f.endswith(".json"):
            ok, found = _explained_json(xml_out[f], py_out[f], packages, moved)
        else:
            ok, found = _explained(xml_out[f], py_out[f], packages, private, moved)
        kinds |= {f"{f}: {k}" for k in found}
        if not ok:
            diff = list(difflib.unified_diff(xml_out[f], py_out[f], "XML", "Python", n=1,
                                             lineterm=""))
            problems.append(f"{f}:\n" + "\n".join("        " + l for l in diff[:20]))
    status = "FAIL" if problems else "PASS"
    print(f"{name} ({suite}): caps {status}" + (f" ({'; '.join(sorted(kinds))})" if kinds else ""),
          file=out)
    for p in problems:
        print(f"    {p}", file=out)
    return not problems


def verify(py_dirs, xml_dirs, scheme_dirs, import_path=(), legacy_mode=False,
           strict=False, out=sys.stdout, write_xml=None, cases=()) -> bool:
    """Compare every Python suite with its XML suite; True if none fails.
    *write_xml*: a directory to write each Python suite's flattened form to,
    as a suite definition file (py2sdf). *cases*: built CAM-SIMA case
    directories whose caps to generate from both forms and compare."""
    add_import_path(import_path)
    index = scheme_meta_index(scheme_dirs)
    py_suites = {os.path.basename(p)[len("suite_"):-3]: p
                 for d in py_dirs for p in sorted(glob.glob(os.path.join(d, "suite_*.py")))}
    xml_suites: dict[str, str] = {}
    for d in xml_dirs:
        for p in sorted(glob.glob(os.path.join(d, "suite_*.xml"))):
            xml_suites.setdefault(os.path.basename(p)[len("suite_"):-4], p)
    ok = True
    moved_by_suite: dict[str, list] = {}
    for name, py_path in py_suites.items():
        xml_path = xml_suites.get(name)
        if xml_path is None:
            print(f"{name}: no XML suite to compare with", file=out)
            continue
        schemes = xml_scheme_names(xml_path)
        missing = sorted({s for s in schemes if s not in index})
        if missing:
            print(f"{name}: FAIL -- no .meta for {', '.join(missing)}", file=out)
            ok = False
            continue
        files = list(dict.fromkeys(index[s] for s in schemes))
        try:
            xml_module = build_module(files, legacy_mode, suites=[xml_path])
            py_module = build_module(files, legacy_mode, py=py_path)
        except Exception as exc:  # report and go on with the other suites
            print(f"{name}: FAIL -- {type(exc).__name__}: {exc}", file=out)
            ok = False
            continue
        if write_xml:
            os.makedirs(write_xml, exist_ok=True)
            for suite in py_module.body.block.ops:
                if isa(suite, ccpp.SuiteOp):
                    with open(os.path.join(write_xml, f"suite_{suite.suite_name.data}.xml"),
                              "w") as f:
                        f.write(suite_xml(suite))
        status, details, moved_by_suite[name] = compare(xml_module, py_module, strict)
        ok &= status == "PASS"
        print(f"{name}: {status}" + (f" ({details[0]})" if status == "PASS" and details else ""),
              file=out)
        if status == "FAIL":
            for line in details:
                print(f"    {line}", file=out)
    unmatched = sorted(set(xml_suites) - set(py_suites))
    if unmatched:
        print(f"XML suites with no Python form: {', '.join(unmatched)}", file=out)
    for case_dir in cases:
        try:
            ok &= verify_case(case_dir, py_suites, xml_suites, moved_by_suite, out)
        except Exception as exc:
            print(f"{case_dir}: FAIL -- {type(exc).__name__}: {exc}", file=out)
            ok = False
    return ok


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--py-dir", nargs="+", required=True)
    parser.add_argument("--xml-dir", nargs="+", required=True)
    parser.add_argument("--scheme-dir", nargs="+", required=True)
    parser.add_argument("--import-path", nargs="*", default=[])
    parser.add_argument("--legacy-mode", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--write-xml", metavar="DIR",
                        help="also write each Python suite as a suite definition file")
    parser.add_argument("--case", nargs="*", default=[], metavar="CASE_DIR",
                        help="built CAM-SIMA cases: generate their caps from both "
                             "forms of their suite and compare")
    args = parser.parse_args(argv)
    ok = verify(args.py_dir, args.xml_dir, args.scheme_dir, args.import_path,
                args.legacy_mode, args.strict, write_xml=args.write_xml, cases=args.case)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
