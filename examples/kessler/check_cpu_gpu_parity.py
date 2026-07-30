#!/usr/bin/env python3
"""Cross-build numerical-parity check for examples/kessler.

Diffs each driver's output between two SEPARATELY CONFIGURED build trees
(typically a CPU build and a GPU build) -- a different comparison from
check_parity.py, which diffs the four different drivers against each other
within one tree. ctest itself can only run tests registered in one build
tree, so this script takes both trees' own kessler build directories as
plain arguments rather than relying on ctest to bridge them; see this
example's own CMakeLists.txt for the optional KESSLER_CPU_GPU_REFERENCE_BUILD
cache variable that registers this as a real ctest test anyway (by pointing
one tree's own CMake configuration at the other tree's path).

A driver that fails to build in one of the two trees (e.g. because that
tree lacks a C++ compiler) is skipped, not treated as a failure -- only
drivers present in BOTH trees are compared. A driver that crashes at
runtime in either tree is reported clearly (captured stdout/stderr shown)
and counts as a failure, but does not stop the other drivers from still
being checked.

The driver list defaults to all four but can be narrowed with an optional
third argument (comma-separated executable names) -- see this example's
own CMakeLists.txt, which passes a reduced list for a GPU-configured tree
(only kessler_ccpp.exe is currently known to work on real GPU hardware;
the other three are masked out of GPU testing for now, not because this
script can't run them, but because they're known to crash there).
"""
import difflib
import subprocess
import sys
from pathlib import Path

DEFAULT_DRIVERS = ["kessler_ccpp.exe", "kessler_hand.exe", "kessler_cxx.exe", "kessler_cxx_host.exe"]


def run_filtered(path):
    result = subprocess.run([str(path)], capture_output=True, text=True)
    if result.returncode != 0:
        return None, result.returncode, result.stdout, result.stderr
    filtered = [line for line in result.stdout.splitlines() if "Elapsed" not in line]
    return filtered, 0, result.stdout, result.stderr


def main():
    if len(sys.argv) not in (3, 4):
        print("usage: check_cpu_gpu_parity.py <build_dir_a>/examples/kessler "
              "<build_dir_b>/examples/kessler [driver1.exe,driver2.exe,...]", file=sys.stderr)
        return 1
    dir_a, dir_b = Path(sys.argv[1]), Path(sys.argv[2])
    drivers = sys.argv[3].split(",") if len(sys.argv) == 4 else DEFAULT_DRIVERS

    ok = True
    compared_any = False
    for driver in drivers:
        exe_a, exe_b = dir_a / driver, dir_b / driver
        if not exe_a.exists() or not exe_b.exists():
            print(f"SKIP: {driver} (not built in one or both of {dir_a}, {dir_b})")
            continue
        compared_any = True

        out_a, rc_a, stdout_a, stderr_a = run_filtered(exe_a)
        out_b, rc_b, stdout_b, stderr_b = run_filtered(exe_b)

        if rc_a != 0 or rc_b != 0:
            ok = False
            print(f"FAIL: {driver} crashed (exit {rc_a} in {dir_a}, exit {rc_b} in {dir_b})")
            if rc_a != 0:
                print(f"  --- {exe_a} stdout ---\n{stdout_a}\n  --- stderr ---\n{stderr_a}")
            if rc_b != 0:
                print(f"  --- {exe_b} stdout ---\n{stdout_b}\n  --- stderr ---\n{stderr_b}")
            continue

        if out_a == out_b:
            print(f"PASS: {driver} (bit-for-bit across the two build trees)")
        else:
            ok = False
            print(f"FAIL: {driver} differs between {dir_a} and {dir_b}")
            sys.stdout.writelines(difflib.unified_diff(
                [line + "\n" for line in out_a], [line + "\n" for line in out_b],
                fromfile=str(exe_a), tofile=str(exe_b)))

    if not compared_any:
        print(f"FAIL: no driver was built in both {dir_a} and {dir_b}", file=sys.stderr)
        return 1
    if ok:
        print("=== All drivers built in both trees produce identical output. ===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
