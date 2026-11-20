"""The suite cap wraps each device call in one present() region over every
device-resident variable that call touches, not one region per variable
(gpu-cap-present-regions): each region is an enter/exit event at run time.

host_a and host_b are device-resident and their schemes disagree:
dev_ab uses both on the device, cpu_ab both on the host, dev_a only host_a
on the device. So dev_ab gets one region over both (suite cap dummies q_a
and q_b), dev_a its own region over q_a (regions are never merged across
calls), and the update self/device syncs around cpu_ab stay outside the
present regions.
"""

import os
import re

import pytest

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.tools.ccpp_dsl import ccppMain


def _arg(local, std, device):
    return f"""\
[ {local} ]
  standard_name = {std}
  units = 1
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension)
  intent = inout
{"  memory_space = device" + chr(10) if device else ""}"""


def _scheme(name, stds, device):
    # local name = the quantity's letter, so the suite cap's dummy
    # arguments (named after the schemes' local names) are q_a and q_b
    args = "".join(_arg("q_" + std[-1], std, device) for std in stds)
    return f"""\
[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_run
  type = scheme
[ ncol ]
  standard_name = horizontal_dimension
  units = count
  type = integer
  dimensions = ()
  intent = in
{args}{CCPP_MANDATORY_ARGS}"""


def _host_var(name, std):
    return f"""\
[ {name} ]
  standard_name = {std}
  units = 1
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension)
  memory_space = device
"""


_HOST = (
    """\
[ccpp-table-properties]
  name = pr_host_mod
  type = module
[ccpp-arg-table]
  name = pr_host_mod
  type = module
[ ncols ]
  standard_name = horizontal_dimension
  units = count
  type = integer
  dimensions = ()
"""
    + _host_var("host_a", "quantity_a")
    + _host_var("host_b", "quantity_b")
)

_SCHEMES = [
    ("dev_ab", ["quantity_a", "quantity_b"], True),
    ("cpu_ab", ["quantity_a", "quantity_b"], False),
    ("dev_a", ["quantity_a"], True),
]


def _suite_cap(tmp_path, directive):
    for name, stds, device in _SCHEMES:
        (tmp_path / f"{name}.meta").write_text(_scheme(name, stds, device))
    (tmp_path / "pr_host_mod.meta").write_text(_HOST)
    (tmp_path / "s.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<suite name="s" version="2.0">\n  <group name="g">\n'
        + "".join(f"    <scheme>{n}</scheme>\n" for n, *_ in _SCHEMES)
        + "  </group>\n</suite>\n"
    )
    tool = ccppMain()
    options_db = tool.default_options_db()
    options_db.update({
        "suites": [str(tmp_path / "s.xml")],
        "scheme_files": [str(tmp_path / f"{n}.meta") for n, *_ in _SCHEMES],
        "host_files": [str(tmp_path / "pr_host_mod.meta")],
        "host_name": "pr_host",
        "out": str(tmp_path / "out"),
        "tempdir": str(tmp_path / "tmp"),
        "verbose": 0,
        "directive": directive,
    })
    result = tool.run(options_db)
    text = next(
        open(os.path.join(options_db["out"], p)).read()
        for p in result.written
        if p.endswith("s_cap.F90")
    )
    return re.sub(r"&\s*\n\s*", "", text)


def _region_before(lines, scheme, begin_re):
    """The present-region directive line directly enclosing scheme's call
    (the nearest begin directive above it, with only preprocessor lines
    and the call's error guard in between), or None."""
    idx = next(i for i, line in enumerate(lines) if f"call {scheme}_run" in line)
    for line in reversed(lines[:idx]):
        stripped = line.strip()
        if re.search(begin_re, stripped):
            return stripped
        if stripped.startswith("#") or stripped.startswith("if (errflg"):
            continue
        return None
    return None


@pytest.mark.parametrize(
    "directive, begin_re",
    [("acc", r"^!\$acc data present\("), ("omp", r"^!\$omp target data map\(alloc:")],
)
def test_one_present_region_per_call(tmp_path, directive, begin_re):
    cap = _suite_cap(tmp_path, directive)
    lines = cap.splitlines()
    regions = [line.strip() for line in lines if re.search(begin_re, line.strip())]
    assert len(regions) == 2, cap

    ab = _region_before(lines, "dev_ab", begin_re)
    assert ab is not None, cap
    assert re.search(r"\bq_a\b", ab) and re.search(r"\bq_b\b", ab), ab

    a = _region_before(lines, "dev_a", begin_re)
    assert a is not None, cap
    assert re.search(r"\bq_a\b", a) and not re.search(r"\bq_b\b", a), a

    # the host call keeps its syncs, outside any present region
    assert _region_before(lines, "cpu_ab", begin_re) is None, cap
    sync = "update self" if directive == "acc" else "target update from"
    assert re.search(sync, cap), cap


@pytest.mark.parametrize(
    "directive, begin_re, end_re",
    [
        ("acc", r"^!\$acc data present\(", r"^!\$acc end data$"),
        ("omp", r"^!\$omp target data map\(alloc:", r"^!\$omp end target data$"),
    ],
)
def test_present_regions_compile_only_with_residency_checks(
    tmp_path, directive, begin_re, end_re
):
    """The present regions are check_only: guarded by CCPP_GPU_PRESENT_CHECKS
    (defined by a host in DEBUG GPU builds), not by USE_GPU."""
    lines = [line.strip() for line in _suite_cap(tmp_path, directive).splitlines()]
    guarded = [
        i for i, line in enumerate(lines)
        if re.search(begin_re, line) or re.search(end_re, line)
    ]
    assert len(guarded) == 4, lines
    for i in guarded:
        assert lines[i - 1] == "#ifdef CCPP_GPU_PRESENT_CHECKS", lines[i - 1 : i + 2]
        assert lines[i + 1] == "#endif", lines[i - 1 : i + 2]
    if directive == "acc":
        # the data movement around the host call stays under USE_GPU
        # (update directives are printed unguarded, as before)
        assert not any(
            line == "#ifdef USE_GPU" and re.search(begin_re, nxt)
            for line, nxt in zip(lines, lines[1:])
        )


def test_check_only_region_rejects_data_movement():
    from xdsl.dialects.test import TestOp
    from xdsl.dialects.builtin import f64
    from xdsl.utils.exceptions import VerifyException

    from xdsl_ccpp.dialects.ccpp_utils import AccDataBeginOp, OmpTargetDataBeginOp

    value = TestOp(result_types=[f64]).results[0]
    AccDataBeginOp(present=[value], check_only=True).verify()
    OmpTargetDataBeginOp(alloc=[value], check_only=True).verify()
    with pytest.raises(VerifyException, match="check_only"):
        AccDataBeginOp(copy=[value], check_only=True).verify()
    with pytest.raises(VerifyException, match="check_only"):
        OmpTargetDataBeginOp(tofrom=[value], check_only=True).verify()
