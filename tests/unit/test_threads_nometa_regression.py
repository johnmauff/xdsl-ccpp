"""Regression test: examples/threads_nometa stays semantically faithful to
examples/threads.

dup-meta-shadow-elim (BACKLOG.md), Phase 6 (adapted). threads_nometa's own
`.meta` is never committed -- it's regenerated from tagged Fortran at
CMake configure time and fed straight into the real build, so there's no
separate committed copy that could ever drift from source the way the
original Phase 6 design (regenerate-and-diff-against-committed-.meta)
assumed. The real, still-valuable check is the one actually run by hand
while building this example: does thread_scheme.F90's regenerated .meta
stay semantically identical to examples/threads' own hand-authored
thread_scheme.meta? This is a fast, compile-free pytest equivalent of
that check -- exactly the kind of thing that would have caught the real
kind-string-spacing bug found and fixed while building this example
(CHANGELOG.md/plan notes), at the pytest-CI level instead of only
discoverable via a full compile.
"""

import pytest

pytest.importorskip("fparser", reason="fparser not installed")

from xdsl_ccpp.tools.ccpp_validate_source import _load_meta_file
from xdsl_ccpp.transforms.fparser2_to_meta import build_meta_module_from_file
from xdsl_ccpp.transforms.validate_source import compare_modules


def test_threads_nometa_matches_threads_hand_authored_meta():
    original = _load_meta_file("examples/threads/thread_scheme.meta")
    regenerated = build_meta_module_from_file(
        "examples/threads_nometa/thread_scheme.F90"
    )
    mismatches = compare_modules(original, regenerated)
    assert mismatches == [], (
        "examples/threads_nometa/thread_scheme.F90's !$ccpp tags no longer "
        "regenerate content matching examples/threads' own hand-authored "
        "thread_scheme.meta:\n" + "\n".join(str(m) for m in mismatches)
    )
