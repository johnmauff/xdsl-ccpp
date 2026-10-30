"""Find code in xdsl_ccpp that nothing runs (BACKLOG dead-code-coverage).

``run`` measures, with coverage.py (branch coverage), which lines of
xdsl_ccpp two workloads execute, kept apart:

- ``generator``: cap generation for built CAM-SIMA cases and, with
  --examples, the xdsl_ccpp_capgen() calls of a configured build tree --
  the same inputs as cap_oracle.py (cases with identical inputs are
  generated once) -- plus the FileCheck tests (tests/filecheck), whose RUN
  lines are the generator's pipelines on every example;
- ``tests``: the rest of the pytest suite (--no-tests skips both pytest
  runs).

The generator and the tests start further Python processes (the frontend,
ccpp_opt's pass pipeline, FileCheck RUN lines); each is measured through a
sitecustomize.py that starts coverage when COVERAGE_PROCESS_START is set,
put on PYTHONPATH for this run only. Normal runs are unaffected.

``report`` sorts every function and method into three groups, from the
lines its body executed:

- run by the generator: live in CAM-SIMA or an example;
- run only by the tests: a feature no case uses, or dead code a test
  keeps alive;
- run by nothing: a removal candidate.

and lists the blocks of a generator-run function that the generator never
reached (a branch no case takes), with whether the tests reach them.
Unreached is not the same as dead: error paths and unused options are
legitimate, and the result depends on which cases are given. Every
candidate needs reading before it is removed. With --vulture, the report
also lists what vulture (a static check for unreferenced names) finds.

    python -m xdsl_ccpp.tools.code_coverage run --out DIR [--examples BUILD_DIR]
        [--no-tests] [-j N] [CASE_DIR...]
    python -m xdsl_ccpp.tools.code_coverage report DIR [--min-block N] [--vulture]

Needs coverage.py, and vulture for --vulture (both in the ``dev`` extra).
"""

from __future__ import annotations

import argparse
import ast
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from xdsl_ccpp.tools.cam_case import read_case
from xdsl_ccpp.tools.cap_oracle import REPO, default_jobs, generate, read_example_calls

PACKAGE = os.path.join(REPO, "xdsl_ccpp")
WORKLOADS = ("generator", "tests")

_SITECUSTOMIZE = "import coverage\ncoverage.process_startup()\n"


def _rcfile(out: str, workload: str) -> str:
    """Write <out>/<workload>/coveragerc and return its path."""
    data_dir = os.path.join(out, workload)
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "coveragerc")
    with open(path, "w") as f:
        f.write(
            "[run]\n"
            "branch = True\n"
            "parallel = True\n"
            f"source = {PACKAGE}\n"
            f"data_file = {os.path.join(data_dir, '.coverage')}\n"
        )
    return path


def _measured_env(out: str, workload: str) -> tuple[str, dict]:
    """(the sitecustomize directory, os.environ plus what starts coverage in
    every Python process of <workload>)."""
    site = os.path.join(out, "site")
    os.makedirs(site, exist_ok=True)
    with open(os.path.join(site, "sitecustomize.py"), "w") as f:
        f.write(_SITECUSTOMIZE)
    path = [site, REPO, *filter(None, os.environ.get("PYTHONPATH", "").split(os.pathsep))]
    return site, dict(
        os.environ,
        COVERAGE_PROCESS_START=_rcfile(out, workload),
        PYTHONPATH=os.pathsep.join(path),
    )


def _combine(out: str, workload: str) -> None:
    import coverage

    cov = coverage.Coverage(config_file=os.path.join(out, workload, "coveragerc"))
    cov.load()  # append to what an earlier step combined
    cov.combine(strict=True)
    cov.save()


def run_generator(out: str, cases: list, jobs: int) -> bool:
    site, env = _measured_env(out, "generator")
    os.environ.update(COVERAGE_PROCESS_START=env["COVERAGE_PROCESS_START"])
    extra_path = tuple(env["PYTHONPATH"].split(os.pathsep))
    unique = {}
    for case in cases:
        unique.setdefault(case.input_key, case)

    def one(item):
        key, case = item
        gen = os.path.join(out, "gen", key.replace(os.sep, "_"))
        ok, err = generate(REPO, case, gen, extra_path=extra_path)
        print(f"{'OK' if ok else 'FAILED':10} {case.label}" + ("" if ok else f"\n{err}"))
        return ok

    with ThreadPoolExecutor(jobs) as pool:
        ok = all(list(pool.map(one, sorted(unique.items()))))
    _combine(out, "generator")
    return ok


def run_tests(out: str) -> bool:
    """The FileCheck tests count as the generator (they run its pipelines on
    the examples); the other tests as the tests."""
    ok = True
    for workload, args in (
        ("generator", ["tests/filecheck"]),
        ("tests", ["tests", "--ignore=tests/filecheck"]),
    ):
        _site, env = _measured_env(out, workload)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
            cwd=REPO, env=env,
        )
        ok = ok and proc.returncode == 0
    for workload in WORKLOADS:
        _combine(out, workload)
    return ok


# --- report -------------------------------------------------------------


def _executed(out: str, workload: str) -> dict[str, tuple[set, set]]:
    """path -> (statement lines, executed lines) for every file of the
    package, measured or not; {} if <workload> was not run."""
    import coverage

    rcfile = os.path.join(out, workload, "coveragerc")
    if not os.path.exists(rcfile):
        return {}
    cov = coverage.Coverage(config_file=rcfile)
    cov.load()
    result = {}
    for root, _dirs, files in os.walk(PACKAGE):
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(root, name)
                try:
                    _f, statements, _excl, missing, _s = cov.analysis2(path)
                except coverage.CoverageException:
                    continue
                result[path] = (set(statements), set(statements) - set(missing))
    return result


def _functions(path: str):
    """(qualified name, def line, body lines) for every function in a file;
    body lines exclude the bodies of nested functions and classes."""
    tree = ast.parse(open(path).read())
    found = []

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{child.name}"
                if not isinstance(child, ast.ClassDef):
                    body = set(range(child.body[0].lineno, child.end_lineno + 1))
                    for inner in ast.walk(child):
                        if inner is not child and isinstance(
                            inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                        ):
                            body -= set(range(inner.body[0].lineno, inner.end_lineno + 1))
                    found.append((name, child.lineno, body))
                visit(child, name + ".")
            else:
                visit(child, prefix)

    visit(tree, "")
    return found


def _blocks(lines: list[int], statements: list[int]) -> list[list[int]]:
    """Runs of consecutive statements (in statement order) from <lines>."""
    wanted = set(lines)
    blocks, current = [], []
    for line in statements:
        if line in wanted:
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def report(out: str, min_block: int, with_vulture: bool) -> str:
    gen, tests = _executed(out, "generator"), _executed(out, "tests")
    groups = {"generator": [], "tests": [], "never": []}
    unreached = []
    totals = []
    for path in sorted(gen.keys() | tests.keys()):
        rel = os.path.relpath(path, REPO)
        statements = (gen.get(path) or tests[path])[0]
        gen_run = gen.get(path, (statements, set()))[1]
        test_run = tests.get(path, (statements, set()))[1]
        totals.append((rel, len(statements), len(gen_run), len(gen_run | test_run)))
        for name, line, body in _functions(path):
            body_statements = sorted(body & statements)
            if not body_statements:
                continue
            where = f"{rel}:{line} {name} ({len(body_statements)} statements)"
            if body & gen_run:
                groups["generator"].append(where)
                for block in _blocks(sorted(set(body_statements) - gen_run), sorted(statements)):
                    if len(block) >= min_block:
                        tested = "tests run it" if set(block) & test_run else "nothing runs it"
                        unreached.append(f"{rel}:{block[0]}-{block[-1]} in {name} "
                                         f"({len(block)} statements; {tested})")
            elif body & test_run:
                groups["tests"].append(where)
            else:
                groups["never"].append(where)

    n_statements = sum(t[1] for t in totals)
    lines = [
        "# xdsl_ccpp code coverage",
        "",
        f"{n_statements} statements: {sum(t[2] for t in totals)} run by the generator, "
        f"{sum(t[3] for t in totals)} by the generator or the tests.",
        f"Functions: {len(groups['generator'])} run by the generator, "
        f"{len(groups['tests'])} only by the tests, {len(groups['never'])} by nothing.",
        "",
        "## Files (statements, % run by the generator, % by either)",
        "",
    ]
    for rel, n, g, e in sorted(totals, key=lambda t: (t[2] / t[1] if t[1] else 1, t[0])):
        if n:
            lines.append(f"- {rel}: {n}, {100 * g // n}%, {100 * e // n}%")
    for title, key in (("Functions nothing runs", "never"),
                       ("Functions only the tests run", "tests")):
        lines += ["", f"## {title} ({len(groups[key])})", ""]
        lines += [f"- {w}" for w in groups[key]]
    lines += ["", f"## Blocks of {min_block}+ statements the generator never reaches, "
              f"in functions it runs ({len(unreached)})", ""]
    lines += [f"- {u}" for u in unreached]
    if with_vulture:
        proc = subprocess.run(
            [sys.executable, "-m", "vulture", PACKAGE, "--min-confidence", "60"],
            cwd=REPO, capture_output=True, text=True,
        )
        found = [os.path.relpath(f, REPO) if f.startswith(PACKAGE) else f
                 for f in proc.stdout.splitlines()]
        lines += ["", f"## vulture, confidence 60%+ ({len(found)})", ""]
        lines += [f"- {f}" for f in found]
    text = "\n".join(lines) + "\n"
    with open(os.path.join(out, "report.md"), "w") as f:
        f.write(text)
    return text


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="measure the generator and the tests")
    run.add_argument("--out", required=True, help="output directory")
    run.add_argument("--examples", metavar="BUILD_DIR",
                     help="also generate the xdsl_ccpp_capgen() calls of this build tree")
    run.add_argument("--no-tests", action="store_true", help="skip the pytest run")
    run.add_argument("--jobs", "-j", type=int, default=default_jobs())
    run.add_argument("cases", nargs="*", metavar="CASE_DIR", help="built CAM-SIMA case directories")
    rep = sub.add_parser("report", help="write <DIR>/report.md from a run")
    rep.add_argument("out", metavar="DIR")
    rep.add_argument("--min-block", type=int, default=3,
                     help="smallest unreached block listed, in statements (default 3)")
    rep.add_argument("--vulture", action="store_true", help="add vulture's findings")
    args = parser.parse_args(argv)

    if args.command == "report":
        report(args.out, args.min_block, args.vulture)
        print(f"wrote {os.path.join(args.out, 'report.md')}")
        return 0

    cases = []
    for case_dir in args.cases:
        try:
            cases.append(read_case(case_dir))
        except FileNotFoundError as err:
            print(f"SKIPPED    {err}")
    if args.examples:
        cases += read_example_calls(args.examples)
    if not cases and args.no_tests:
        parser.error("run: nothing to measure")
    ok = run_generator(args.out, cases, args.jobs) if cases else True
    if not args.no_tests:
        ok = run_tests(args.out) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
