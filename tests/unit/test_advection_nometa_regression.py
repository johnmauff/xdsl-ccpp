"""Regression test: examples/advection_nometa stays semantically faithful
to examples/advection, for all 5 real schemes.

dup-meta-shadow-elim (BACKLOG.md), Phase 7. Each scheme's own `.meta` is
never committed in examples/advection_nometa -- it's regenerated from
tagged Fortran at CMake configure time and fed straight into the real
build, so there's no separate committed copy that could ever drift from
source. The real, still-valuable check is the one actually run by hand
while building this example: does each scheme's regenerated .meta stay
semantically identical to examples/advection's own hand-authored .meta
for that same scheme? This is a fast, compile-free pytest equivalent of
that check, exactly as test_threads_nometa_regression.py already does
for the single-scheme threads/threads_nometa pair -- extended here to
loop over all 5 real schemes this suite actually has.
"""

import pytest

pytest.importorskip("fparser", reason="fparser not installed")

from xdsl_ccpp.tools.ccpp_validate_source import _load_meta_file
from xdsl_ccpp.transforms.fparser2_to_meta import build_meta_module_from_file
from xdsl_ccpp.transforms.validate_source import compare_modules


SCHEMES = [
    "const_indices",
    "cld_liq",
    "apply_constituent_tendencies",
    "cld_ice",
    "cld_shadow",
]


@pytest.mark.parametrize("scheme", SCHEMES)
def test_advection_nometa_matches_advection_hand_authored_meta(scheme):
    original = _load_meta_file(f"examples/advection/{scheme}.meta")
    regenerated = build_meta_module_from_file(
        f"examples/advection_nometa/{scheme}.F90"
    )
    mismatches = compare_modules(original, regenerated)
    assert mismatches == [], (
        f"examples/advection_nometa/{scheme}.F90's !$ccpp tags no longer "
        f"regenerate content matching examples/advection's own "
        f"hand-authored {scheme}.meta:\n"
        + "\n".join(str(m) for m in mismatches)
    )
