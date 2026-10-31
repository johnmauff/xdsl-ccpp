"""Check that a change to xdsl-ccpp generates the caps it should for real
CAM-SIMA cases.

``diff``: regenerate each case's caps with a base revision of xdsl-ccpp and
with the working tree, and compare the generated files. For a refactor the
expected result is "identical" everywhere; any difference is listed with its
diff, so a deliberate change can be reviewed. The base revision is exported
with ``git archive`` (the repository is not touched), and each revision runs
in its own subprocess. Cases whose generator inputs are identical (e.g. the
gnu, intel and nvhpc copies of an FPHYStest case) are generated once, and
distinct cases are generated in parallel (--jobs).

``capgen``: generate each case's caps with original capgen (the
ccpp_framework in the case's own CAM-SIMA checkout) and with the working
tree's xdsl-ccpp, and compare what the code does (cap_compare.py): scheme
calls per phase and the expression each argument receives. Cases capgen
cannot generate (Python suites, package caps, xdsl-only metadata such as
memory_space) are reported, not compared. GPU cases are compared without
--directive.

Cases are built CAM-SIMA case directories: their build cache records the
generator inputs (see cam_case.py). ``diff --examples BUILD_DIR`` also
regenerates every xdsl_ccpp_capgen() call of a configured CMake build tree
of this repository (examples/), from the command each call records at
configure time (cmake/xdsl_ccpp_capgen.cmake). Generation only -- nothing
is compiled.

    python -m xdsl_ccpp.tools.cap_oracle diff [--base main] [--out DIR] [-j N]
        [--examples BUILD_DIR] [CASE_DIR...]
    python -m xdsl_ccpp.tools.cap_oracle capgen [--out DIR] [-j N] CASE_DIR...

Exit status: 0 if every case generates identically (diff) or equivalently
(capgen), 1 otherwise.
"""

from __future__ import annotations

import argparse
import dataclasses
import difflib
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from xdsl_ccpp.tools.cap_compare import compare
from xdsl_ccpp.tools.cam_case import CamCase, generator_args, read_case, suite_groups

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def export_revision(repo: str, ref: str, dest: str) -> str:
    """Export <ref>'s tree into <dest> (no change to the repository)."""
    os.makedirs(dest, exist_ok=True)
    archive = subprocess.run(["git", "-C", repo, "archive", ref],
                             check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", dest], input=archive, check=True)
    return dest


EXAMPLE_COMMAND_FILE = "xdsl_ccpp_command.txt"


@dataclasses.dataclass(frozen=True)
class ExampleCall:
    """One xdsl_ccpp_capgen() call of a configured build tree, as CMake
    recorded it in <output dir>/xdsl_ccpp_command.txt: the generator
    arguments (without the output-location flags) and the directory they
    are relative to."""
    name: str                  # output directory, relative to the build tree
    cwd: str
    args: tuple[str, ...]

    @property
    def label(self) -> str:
        return self.name

    @property
    def input_key(self) -> str:
        return self.name


def read_example_calls(build_dir: str) -> list[ExampleCall]:
    """Every recorded xdsl_ccpp_capgen() call under a configured build tree."""
    calls = []
    for root, _dirs, files in sorted(os.walk(build_dir)):
        if EXAMPLE_COMMAND_FILE not in files:
            continue
        cwd, args = None, []
        for line in open(os.path.join(root, EXAMPLE_COMMAND_FILE)).read().splitlines():
            key, _, value = line.partition("=")
            if key == "cwd":
                cwd = value
            elif key == "arg":
                args.append(value)
        if cwd is None:
            raise ValueError(f"{root}/{EXAMPLE_COMMAND_FILE}: no cwd= line")
        calls.append(ExampleCall(os.path.relpath(root, build_dir), cwd, tuple(args)))
    return calls


@lru_cache
def _accepts_jobs(src_tree: str) -> bool:
    """Whether <src_tree>'s ccpp_dsl has --jobs (an older --base may not)."""
    try:
        return '"--jobs"' in open(os.path.join(src_tree, "xdsl_ccpp", "tools", "ccpp_dsl.py")).read()
    except OSError:
        return False


def generate(src_tree: str, case: "CamCase | ExampleCall", out_dir: str,
             extra_path: tuple[str, ...] = (), jobs: int = 1) -> tuple[bool, str]:
    """Generate <case>'s caps with the xdsl-ccpp in <src_tree>, with
    <extra_path> after it on PYTHONPATH (code_coverage.py's measurement
    hook) and ccpp_dsl --jobs <jobs> when above 1 and the tree has it.
    Returns (success, the end of stderr)."""
    os.makedirs(out_dir, exist_ok=True)
    if isinstance(case, ExampleCall):
        args = [*case.args, "-o", out_dir, "--tempdir", os.path.join(out_dir, "tmp"),
                "--emit-datatable", os.path.join(out_dir, "datatable.xml")]
        cwd, path = case.cwd, (src_tree,)
    else:
        args, cwd, path = generator_args(case, out_dir), src_tree, (src_tree, *case.python_path)
    if jobs > 1 and _accepts_jobs(src_tree):
        args = [*args, "--jobs", str(jobs)]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((*path, *extra_path)))
    proc = subprocess.run(
        [sys.executable, "-m", "xdsl_ccpp.tools.ccpp_dsl", *args],
        cwd=cwd, env=env, capture_output=True, text=True,
    )
    return proc.returncode == 0, "\n".join(proc.stderr.splitlines()[-5:])


def generated_files(out_dir: str) -> dict[str, str]:
    """Generated file name -> path (the top-level files; tmp/ is scratch)."""
    return {f: os.path.join(out_dir, f) for f in sorted(os.listdir(out_dir))
            if os.path.isfile(os.path.join(out_dir, f))}


def _read(path: str, paths: dict[str, str]) -> list[str]:
    """A generated file's lines, with run-specific absolute paths (the
    output directory, the xdsl-ccpp tree; the datatable records both)
    replaced by placeholders."""
    text = open(path).read()
    for real, placeholder in paths.items():
        text = text.replace(real, placeholder)
    return text.splitlines(True)


def compare_dirs(base_dir: str, head_dir: str, base_tree: str = "", head_tree: str = ""
                 ) -> list[tuple[str, list[str]]]:
    """[(file, unified diff lines)] for every file that differs, is missing
    or is new."""
    base, head = generated_files(base_dir), generated_files(head_dir)
    # The head tree also appears on the base side: an example's inputs are
    # read from the working tree by both revisions.
    base_paths = {p: v for p, v in ((base_dir, "<out>"), (base_tree, "<xdsl-ccpp>"),
                                    (head_tree, "<xdsl-ccpp>")) if p}
    head_paths = {p: v for p, v in ((head_dir, "<out>"), (head_tree, "<xdsl-ccpp>")) if p}
    diffs = []
    for name in sorted(set(base) | set(head)):
        a = _read(base[name], base_paths) if name in base else []
        b = _read(head[name], head_paths) if name in head else []
        if a != b:
            diffs.append((name, list(difflib.unified_diff(
                a, b, f"base/{name}", f"head/{name}"))))
    return diffs


def _check(group: list[CamCase], key: str, gen_jobs: int, base_tree: str,
           head_tree: str, out: str) -> tuple[bool, str]:
    """Generate one distinct case with both revisions (ccpp_dsl --jobs
    <gen_jobs>) and compare. Returns (identical, report line)."""
    case = group[0]
    name = f"{case.label}-{key}"
    dirs = {rev: os.path.join(out, name, rev) for rev in ("base", "head")}
    results = {rev: generate(tree, case, dirs[rev], jobs=gen_jobs)
               for rev, tree in (("base", base_tree), ("head", head_tree))}
    shared = f" (+{len(group) - 1} cases with the same inputs)" if len(group) > 1 else ""
    ok = {rev: r[0] for rev, r in results.items()}
    if not ok["base"] and not ok["head"]:
        return True, f"BOTH FAIL  {case.label}{shared}: generation fails before and after"
    if ok["base"] != ok["head"]:
        bad = "head" if ok["base"] else "base"
        return False, (f"CHANGED    {case.label}{shared}: generation fails with {bad} only\n"
                       f"           {results[bad][1]}")
    diffs = compare_dirs(dirs["base"], dirs["head"],
                         os.path.abspath(base_tree), os.path.abspath(head_tree))
    if not diffs:
        return True, f"IDENTICAL  {case.label}{shared}"
    diff_path = os.path.join(out, name, "diff.txt")
    with open(diff_path, "w") as f:
        for _, lines in diffs:
            f.writelines(lines)
    summary = ", ".join(
        f"{fname} ({sum(1 for l in lines if l[:1] in '+-' and l[:3] not in ('+++', '---'))} lines)"
        for fname, lines in diffs)
    return False, f"DIFFERENT  {case.label}{shared}: {summary}\n           {diff_path}"


def generation_jobs(jobs: int, n_cases: int) -> int:
    """ccpp_dsl --jobs for each generation: the <jobs> CPUs shared among the
    generations that run at once, so a run of few cases still uses them all
    (1 case: <jobs>; as many cases as <jobs> or more: 1)."""
    return max(1, jobs // max(1, min(jobs, n_cases)))


def _run_checks(cases: list[CamCase], check, report, jobs: int) -> bool:
    """Run check(group, key, gen_jobs) for each distinct case (cases with the
    same inputs grouped), <jobs> at a time, each generation using
    generation_jobs CPUs; report in case order. True if all checks passed."""
    by_key: dict[str, list[CamCase]] = {}
    for case in cases:
        by_key.setdefault(case.input_key, []).append(case)
    gen_jobs = generation_jobs(jobs, len(by_key))
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = [pool.submit(check, group, key, gen_jobs) for key, group in by_key.items()]
        passed = True
        for future in futures:
            ok, line = future.result()
            passed &= ok
            report(line)
    return passed


def run_diff(cases: list[CamCase], base_tree: str, head_tree: str, out: str,
             report=print, jobs: int = 1) -> bool:
    """Generate and compare every distinct case with both revisions; True if
    all identical."""
    return _run_checks(
        cases, lambda group, key, gen_jobs: _check(group, key, gen_jobs, base_tree, head_tree, out),
        report, jobs)


# Runs original capgen as cam_autogen.py does; arguments as JSON on stdin.
# Exit status 2: capgen rejected the input (CCPPError, e.g. xdsl-only
# metadata); any other failure is an error in running it.
_CAPGEN = """
import json, logging, sys
a = json.load(sys.stdin)
sys.path.insert(0, a["scripts"])
from ccpp_capgen import capgen
from framework_env import CCPPFrameworkEnv
from parse_tools import CCPPError
logging.basicConfig(level=logging.WARNING)
env = CCPPFrameworkEnv(logging.getLogger("capgen"), host_files=a["host_files"],
                       scheme_files=a["scheme_files"], suites=a["suites"],
                       preproc_directives=a["preproc_defs"], generate_docfiles=False,
                       host_name="cam", kind_types=["kind_phys = REAL64"],
                       use_error_obj=False, force_overwrite=False,
                       output_root=a["out"], ccpp_datafile=a["out"] + "/ccpp_datatable.xml")
try:
    capgen(env, return_db=True)
except CCPPError as err:
    print(err, file=sys.stderr)
    sys.exit(2)
"""


def run_capgen(case: CamCase, out_dir: str) -> tuple[str, str]:
    """Generate <case>'s caps with original capgen from the case's own
    CAM-SIMA checkout. Returns ("ok" | "rejected" | "error", the end of
    stderr); "rejected" is capgen refusing the input."""
    os.makedirs(out_dir, exist_ok=True)
    args = {"scripts": os.path.join(os.path.dirname(case.framework_src_dir), "scripts"),
            "host_files": list(case.host_files), "scheme_files": list(case.scheme_files),
            "suites": list(case.suite_files), "preproc_defs": list(case.preproc_defs),
            "out": out_dir}
    proc = subprocess.run([sys.executable, "-c", _CAPGEN], input=json.dumps(args),
                          cwd=out_dir, capture_output=True, text=True)
    status = {0: "ok", 2: "rejected"}.get(proc.returncode, "error")
    return status, "\n".join(proc.stderr.splitlines()[-3:])


def _check_capgen(group: list[CamCase], key: str, gen_jobs: int, head_tree: str,
                  out: str) -> tuple[bool, str]:
    """Generate one distinct case with capgen and the working tree's
    xdsl-ccpp (ccpp_dsl --jobs <gen_jobs>), and compare. Returns
    (equivalent, report line)."""
    case = group[0]
    shared = f" (+{len(group) - 1} cases with the same inputs)" if len(group) > 1 else ""
    name = f"{case.suite}-{key}"
    dirs = {g: os.path.join(out, name, g) for g in ("capgen", "xdsl")}
    status, err = run_capgen(case, dirs["capgen"])
    if status == "rejected":
        return True, f"NO CAPGEN  {case.suite}{shared}: capgen rejects it: {err.splitlines()[-1] if err else ''}"
    if status == "error":
        return False, f"ERROR      {case.suite}{shared}: running capgen failed\n           {err}"
    ok_xdsl, err = generate(head_tree, case, dirs["xdsl"], jobs=gen_jobs)
    if not ok_xdsl:
        return False, f"XDSL FAILS {case.suite}{shared}: capgen generates it, xdsl-ccpp does not\n           {err}"
    diffs, renames = compare(dirs["capgen"], dirs["xdsl"], suite_groups(case))
    renamed = f" ({len(renames)} cap variables named differently)" if renames else ""
    if not diffs:
        return True, f"EQUIVALENT {case.suite}{shared}{renamed}"
    path = os.path.join(out, name, "differences.txt")
    with open(path, "w") as f:
        f.write("\n".join(diffs) + "\n")
        f.writelines(f"rename: capgen {a} = xdsl {b}\n" for a, b in renames)
    return False, f"DIFFERENT  {case.suite}{shared}: {len(diffs)} differences{renamed}\n           {path}"


def run_capgen_check(cases: list[CamCase], head_tree: str, out: str, report=print,
                     jobs: int = 1) -> bool:
    """Compare each distinct case's xdsl-ccpp caps with original capgen's;
    True if all equivalent. Python-suite and package-cap cases are skipped;
    GPU cases are compared as CPU cases."""
    comparable = []
    for case in cases:
        if case.py_suite or case.package_caps:
            report(f"SKIPPED    {case.label}: capgen has no Python suites or package caps")
        else:
            comparable.append(dataclasses.replace(case, directive=None))
    return _run_checks(
        comparable, lambda group, key, gen_jobs: _check_capgen(group, key, gen_jobs, head_tree, out),
        report, jobs)


def _cpu_quota() -> float | None:
    """This user's cgroup CPU quota in CPUs (cgroup v2 cpu.max or v1
    cpu.cfs_quota_us), or None if unlimited or unknown. Derecho login nodes
    allow 8 CPUs per user."""
    try:
        cgroup = open("/proc/self/cgroup").read().splitlines()
    except OSError:
        return None
    for line in cgroup:
        _, controllers, path = line.split(":", 2)
        if controllers == "":                      # cgroup v2
            try:
                quota, period = open(f"/sys/fs/cgroup{path}/cpu.max").read().split()
            except (OSError, ValueError):
                continue
            return None if quota == "max" else int(quota) / int(period)
        if "cpu" in controllers.split(","):        # cgroup v1
            base = f"/sys/fs/cgroup/{controllers}{path}"
            try:
                quota = int(open(f"{base}/cpu.cfs_quota_us").read())
                period = int(open(f"{base}/cpu.cfs_period_us").read())
            except (OSError, ValueError):
                continue
            return None if quota <= 0 else quota / period
    return None


def default_jobs() -> int:
    """Half the CPUs this user may use (leaving room for builds and other
    work on a shared node): 4 on a Derecho login node, whose per-user quota
    is 8 CPUs. Not os.cpu_count() or nproc: the first ignores the quota, the
    second follows OMP_NUM_THREADS."""
    cpus = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count() or 1
    quota = _cpu_quota()
    if quota is not None:
        cpus = min(cpus, int(quota))
    return max(1, cpus // 2)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    diff = sub.add_parser("diff", help="compare generated caps: base revision vs working tree")
    diff.add_argument("--base", default="main", help="git revision to compare against (default: main)")
    diff.add_argument("--examples", metavar="BUILD_DIR",
                      help="also regenerate the xdsl_ccpp_capgen() calls of this configured "
                           "CMake build tree (examples/)")
    diff.add_argument("cases", nargs="*", metavar="CASE_DIR", help="built CAM-SIMA case directories")
    capgen = sub.add_parser("capgen", help="compare the working tree's caps with original capgen's")
    capgen.add_argument("cases", nargs="+", metavar="CASE_DIR", help="built CAM-SIMA case directories")
    for p in sub.choices.values():
        p.add_argument("--repo", default=REPO, help="xdsl-ccpp repository (default: this one)")
        p.add_argument("--out", help="output directory (default: a new temporary directory)")
        p.add_argument("--jobs", "-j", type=int, default=default_jobs(),
                       help="cases generated at once (default: half the CPUs available "
                            "to this user, %(default)s here)")
    args = parser.parse_args(argv)
    if args.command == "diff" and not (args.cases or args.examples):
        parser.error("diff: give CASE_DIR(s), --examples BUILD_DIR, or both")

    out = args.out or tempfile.mkdtemp(prefix="cap_oracle_")
    cases = []
    for case_dir in args.cases:
        try:
            cases.append(read_case(case_dir))
        except FileNotFoundError as err:
            print(f"SKIPPED    {err}")
    if args.command == "capgen":
        print(f"capgen vs {args.repo} (working tree); output in {out}")
        return 0 if run_capgen_check(cases, args.repo, out, jobs=args.jobs) else 1
    if args.examples:
        examples = read_example_calls(args.examples)
        if not examples:
            print(f"SKIPPED    {args.examples}: no {EXAMPLE_COMMAND_FILE} (configure the build "
                  f"tree with this revision's cmake/xdsl_ccpp_capgen.cmake)")
        cases += examples
    base_tree = export_revision(args.repo, args.base, os.path.join(out, "base_src"))
    print(f"base {args.base}, head {args.repo} (working tree); output in {out}")
    return 0 if run_diff(cases, base_tree, args.repo, out, jobs=args.jobs) else 1


if __name__ == "__main__":
    sys.exit(main())
