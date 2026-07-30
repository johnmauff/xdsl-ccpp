#!/usr/bin/env python3
"""Numerical-parity check for examples/kessler's four drivers.

Mirrors the existing Makefile's own `make check` target exactly: run each
driver, strip the "Elapsed time" line (the only line expected to vary
run-to-run), and diff the CCPP Fortran driver's output against each of the
other three. All three must match bit-for-bit -- a mismatch here is a real
numerical regression, not noise.
"""
import difflib
import subprocess
import sys


def run_filtered(path):
    result = subprocess.run([path], capture_output=True, text=True, check=True)
    return [line for line in result.stdout.splitlines() if "Elapsed" not in line]


def main():
    if len(sys.argv) != 5:
        print("usage: check_parity.py <ccpp_exe> <hand_exe> <cxx_exe> <cxx_host_exe>",
              file=sys.stderr)
        return 1
    ccpp_exe, hand_exe, cxx_exe, cxx_host_exe = sys.argv[1:5]

    ccpp_out = run_filtered(ccpp_exe)
    ok = True
    for label, exe in (("hand", hand_exe), ("cxx", cxx_exe), ("cxx_host", cxx_host_exe)):
        other_out = run_filtered(exe)
        if other_out == ccpp_out:
            print(f"PASS: ccpp == {label} (bit-for-bit)")
        else:
            print(f"FAIL: ccpp != {label}")
            sys.stdout.writelines(difflib.unified_diff(
                [line + "\n" for line in ccpp_out],
                [line + "\n" for line in other_out],
                fromfile="ccpp", tofile=label))
            ok = False

    if ok:
        print("=== All four drivers produce identical numerical output. ===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
