#!/usr/bin/env python3
"""Mechanically regenerate a filecheck golden fixture from its own real
pipeline output.

Built for task #28 (6-to-8-phase lifecycle match with capgen-v1): each
remaining stage (3-5) changes the lifecycle dispatch shape again, and each
time, roughly a dozen-plus fixtures need their CHECK block updated to match
-- purely mechanical work that Stages 1-2 did by hand (via forked agents
re-deriving the same "CHECK on the first line after a label/blank-line gap,
CHECK-NEXT elsewhere" pattern from scratch each time). This script automates
that pattern directly.

Safety rule (the reason this isn't just "diff and overwrite"): only
fixtures classified as "literal-mirror" style -- CHECK-NEXT lines already
dominate the file, i.e. it already asserts on nearly every generated line --
are eligible for full regeneration. Fixtures classified as "sparse" --
deliberately asserting only a handful of properties, e.g. a single
CHECK-LABEL with no CHECK-NEXT follow-through -- are NEVER auto-rewritten.
Blind literal regeneration previously corrupted one of these (task #28
Stage 1, kessler-bindC.mlir: 52 real lines -> 655 CHECK-NEXT lines) before
being caught and reverted. This script would have refused to touch that
file at all.

Usage:
    python3 scripts/regen_fixture.py FIXTURE.mlir [FIXTURE2.mlir ...]
    python3 scripts/regen_fixture.py FIXTURE.mlir --apply
    python3 scripts/regen_fixture.py FIXTURE.mlir --threshold 0.4
    python3 scripts/regen_fixture.py FIXTURE.mlir --label-regex 'void \\w+\\('

Without --apply: reports each fixture's classification and, for
literal-mirror fixtures with a real diff against current pipeline output,
prints a unified diff of what would change. Nothing is written.

With --apply: rewrites literal-mirror fixtures in place. Sparse fixtures are
still only reported, never touched, regardless of --apply.

Run with the repo's dedicated venv on PATH (RUN: lines invoke `python3 -m
xdsl_ccpp...`, which must resolve to this checkout's own install):
    export PATH="/Users/dennis/Desktop/Work/Claude-Vocabulary/.venv-xdsl-ccpp/bin:$PATH"
"""

from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CHECK_DIRECTIVE_RE = re.compile(r"^(\s*//\s*)(CHECK-LABEL|CHECK-NEXT|CHECK):\s?(.*)$")
RUN_LINE_RE = re.compile(r"^\s*//\s*RUN:\s*(.*)$")

# Anchor patterns: a real-output line matching any of these starts a fresh
# CHECK-LABEL, the same re-sync points a human has been choosing by hand
# across Stages 1-2 (module/subroutine/function boundaries, MLIR func/module
# ops, and the "// FILE: x" markers separating concatenated per-file dumps
# in end-to-end fixtures). Override with --label-regex for a fixture whose
# target dialect doesn't match any of these (e.g. a C header's bare
# "void foo(" declarations).
#
# Split into two groups because the observed convention differs by dialect:
# after a Fortran subroutine/module/function signature, the first body line
# is soft-matched with CHECK (not CHECK-NEXT) even when real output has NO
# blank line there -- likely because Fortran signatures wrap across
# continuation lines ("&"), so pinning the exact wrap point would be
# fragile. After an MLIR func.func/builtin.module/"// FILE:" anchor, real
# output has no such gap, and the observed convention (confirmed against
# fork-authored fixtures) uses a strict CHECK-NEXT immediately -- forcing a
# soft resync there would diverge from real, human-authored fixtures on
# every regen, defeating the idempotency this script depends on.
FORTRAN_LABEL_PATTERNS = [
    r"^\s*module\s+\w",
    r"^\s*subroutine\s+\w",
    r"^\s*(pure\s+|elemental\s+|recursive\s+)*function\s+\w",
]
STRUCTURAL_LABEL_PATTERNS = [
    r"^// FILE: ",
    r"^\s*func\.func\b",
    r"^\s*builtin\.module\b",
]
DEFAULT_LABEL_PATTERNS = FORTRAN_LABEL_PATTERNS + STRUCTURAL_LABEL_PATTERNS

# Lines that are pure noise in real pipeline output -- never emitted as a
# CHECK line, but (like a blank line) they do count as a "gap" that forces
# the next real line back to CHECK (soft resync) instead of CHECK-NEXT.
SEPARATOR_RE = re.compile(r"^// -+$")


def get_run_command(fixture_text: str) -> str:
    """Return the fixture's own RUN: command, with the trailing
    `| python3 -m filecheck ...` stage stripped off (we want the raw
    pipeline output, not filecheck's own pass/fail result)."""
    for line in fixture_text.splitlines():
        m = RUN_LINE_RE.match(line)
        if m:
            cmd = m.group(1)
            # Drop the final filecheck stage (and anything after it).
            cmd = re.sub(r"\|\s*python3\s+-m\s+filecheck\b.*$", "", cmd).rstrip()
            return cmd
    raise ValueError("no `// RUN:` line found in fixture")


def run_pipeline(cmd: str) -> str:
    proc = subprocess.run(
        cmd, shell=True, cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"pipeline exited {proc.returncode}\ncmd: {cmd}\nstderr:\n{proc.stderr}"
        )
    return proc.stdout


def classify_style(fixture_text: str, threshold: float) -> tuple[str, float]:
    """Return ("literal-mirror" | "sparse", check_next_ratio).

    Ratio = CHECK-NEXT lines / all CHECK*-directive lines. A file that's
    mostly CHECK-LABEL/CHECK with few CHECK-NEXT follow-throughs is
    asserting sparse properties, not mirroring its output -- never safe to
    blindly regenerate in full.
    """
    total = 0
    next_count = 0
    for line in fixture_text.splitlines():
        m = CHECK_DIRECTIVE_RE.match(line)
        if not m:
            continue
        total += 1
        if m.group(2) == "CHECK-NEXT":
            next_count += 1
    ratio = (next_count / total) if total else 0.0
    return ("literal-mirror" if ratio >= threshold else "sparse", ratio)


def regenerate_check_lines(
    real_output: str, label_patterns: list[str], fortran_label_patterns: list[str],
) -> list[str]:
    """Turn real pipeline stdout into a list of `// CHECK...:` lines,
    following the pattern already validated by hand across Stages 1-2:
    CHECK-LABEL at each recognized anchor, CHECK on the first real line
    after a blank-line gap (or after a Fortran-style label -- see
    FORTRAN_LABEL_PATTERNS' docstring for why those two cases differ),
    CHECK-NEXT for each subsequent contiguous line.
    """
    label_re = re.compile("(" + ")|(".join(label_patterns) + ")")
    fortran_label_re = re.compile("(" + ")|(".join(fortran_label_patterns) + ")") if fortran_label_patterns else None
    out: list[str] = []
    need_resync = True  # first real line is always a soft CHECK, not NEXT
    for raw_line in real_output.splitlines():
        if raw_line.strip() == "" or SEPARATOR_RE.match(raw_line):
            need_resync = True
            continue
        is_label = bool(label_re.match(raw_line))
        if is_label:
            directive = "CHECK-LABEL"
        elif need_resync:
            directive = "CHECK"
        else:
            directive = "CHECK-NEXT"
        out.append(f"// {directive}: {raw_line}")
        if is_label:
            # Explicitly (re)set, not left over from before this label:
            # a Fortran-style label always forces a soft resync for the
            # line after it; a structural one (func.func/builtin.module/
            # "// FILE:") never does on its own -- only an actual blank
            # line/separator does that (handled above).
            need_resync = bool(fortran_label_re is not None and fortran_label_re.match(raw_line))
        else:
            need_resync = False
    return out


def replace_check_block(fixture_text: str, new_check_lines: list[str]) -> str:
    """Replace every existing `// CHECK...:` line in the fixture with
    new_check_lines, preserving everything else (header comments, the
    RUN: line, blank lines, non-CHECK prose) exactly as-is. The first
    CHECK line's position marks where the replacement block is spliced in;
    trailing CHECK lines are removed, non-CHECK lines in between are left
    untouched at their original relative position after the block.
    """
    lines = fixture_text.splitlines()
    check_idxs = [i for i, l in enumerate(lines) if CHECK_DIRECTIVE_RE.match(l)]
    if not check_idxs:
        raise ValueError("fixture has no existing CHECK lines to anchor the splice")
    first, last = check_idxs[0], check_idxs[-1]
    # Keep any non-CHECK lines that were interleaved among the old CHECK
    # lines (e.g. a stray blank/comment) by appending them after the new
    # block, in their original order -- matches the "preserve everything
    # not being replaced" contract above.
    interleaved_extra = [lines[i] for i in range(first, last + 1) if not CHECK_DIRECTIVE_RE.match(lines[i])]
    new_lines = lines[:first] + new_check_lines + interleaved_extra + lines[last + 1:]
    return "\n".join(new_lines) + ("\n" if fixture_text.endswith("\n") else "")


def process_fixture(
    path: Path, threshold: float, label_patterns: list[str],
    fortran_label_patterns: list[str], apply: bool,
) -> bool:
    """Return True if the fixture now matches (or was already matching)."""
    text = path.read_text()
    style, ratio = classify_style(text, threshold)
    try:
        rel = path.relative_to(REPO_ROOT) if path.is_absolute() else path
    except ValueError:
        rel = path

    if style == "sparse":
        print(f"[sparse, ratio={ratio:.2f}] {rel} -- SKIPPED (never auto-rewritten; hand-edit this one)")
        return False

    try:
        cmd = get_run_command(text)
        real_output = run_pipeline(cmd)
    except (ValueError, RuntimeError) as exc:
        print(f"[error] {rel}: {exc}")
        return False

    new_check_lines = regenerate_check_lines(real_output, label_patterns, fortran_label_patterns)
    try:
        new_text = replace_check_block(text, new_check_lines)
    except ValueError as exc:
        print(f"[error] {rel}: {exc}")
        return False

    if new_text == text:
        print(f"[literal-mirror, ratio={ratio:.2f}] {rel} -- already up to date")
        return True

    if apply:
        path.write_text(new_text)
        print(f"[literal-mirror, ratio={ratio:.2f}] {rel} -- REWRITTEN")
    else:
        diff = difflib.unified_diff(
            text.splitlines(keepends=True), new_text.splitlines(keepends=True),
            fromfile=str(rel), tofile=str(rel) + " (regenerated)",
        )
        print(f"[literal-mirror, ratio={ratio:.2f}] {rel} -- WOULD CHANGE (pass --apply to write):")
        sys.stdout.writelines(diff)
    return apply


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixtures", nargs="+", type=Path)
    ap.add_argument("--apply", action="store_true", help="write changes instead of printing a diff")
    ap.add_argument(
        "--threshold", type=float, default=0.7,
        help="minimum CHECK-NEXT-line ratio to classify a fixture as literal-mirror (default: 0.7; "
             "empirically, a confirmed-safe fixture measured ~0.90, a confirmed-curated one measured "
             "~0.32 -- 0.7 deliberately sits close to the safe side, erring toward flagging a fixture "
             "as sparse rather than risking a bad auto-rewrite)",
    )
    ap.add_argument(
        "--label-regex", action="append", dest="label_patterns", default=None,
        help="extra regex (may repeat) matching a line that should start a new CHECK-LABEL block "
             "with strict CHECK-NEXT immediately after (the 'structural', MLIR-like convention); "
             "adds to, does not replace, the built-in defaults",
    )
    ap.add_argument(
        "--label-regex-fortran", action="append", dest="fortran_label_patterns", default=None,
        help="like --label-regex, but for a label after which the first body line should be a "
             "soft CHECK instead of CHECK-NEXT (the Fortran-signature convention -- see "
             "FORTRAN_LABEL_PATTERNS' docstring)",
    )
    args = ap.parse_args()

    label_patterns = list(DEFAULT_LABEL_PATTERNS)
    if args.label_patterns:
        label_patterns.extend(args.label_patterns)
    fortran_label_patterns = list(FORTRAN_LABEL_PATTERNS)
    if args.fortran_label_patterns:
        label_patterns.extend(args.fortran_label_patterns)
        fortran_label_patterns.extend(args.fortran_label_patterns)

    all_ok = True
    for fixture in args.fixtures:
        ok = process_fixture(
            fixture.resolve(), args.threshold, label_patterns, fortran_label_patterns, args.apply,
        )
        all_ok = all_ok and ok
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
