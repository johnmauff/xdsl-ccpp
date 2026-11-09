"""Dynamic constituent arrays that share a local name.

Register-phase `ccpp_constituent_properties_t` arguments are cap-owned
(never host-matched); their identity is the standard name. Schemes may give
different ones the same local name (atmospheric_physics' suite_rrtmgp:
cfc_constituent_stub, ozone_constituent_stub and initialize_constituents
all call theirs `constituents`). capgen keeps them as distinct host-cap
locals; xdsl-ccpp used to stop with "Suite dummy-argument name collision"
(xdsl76g rrtmgp). Here examples/advection's cld_ice is changed to call its
array `dyn_const`, the name cld_liq's (different) array already has."""

import re
import shutil
from pathlib import Path

from xdsl_ccpp.tools.ccpp_dsl import ccppMain

_EX = Path(__file__).resolve().parents[2] / "examples" / "advection"
_SCHEMES = ["const_indices", "cld_liq", "apply_constituent_tendencies", "cld_ice", "cld_shadow"]
_HOSTS = ["test_host_data", "test_host_mod", "test_host"]


def _generate(tmp_path, rename: bool) -> str:
    src = tmp_path / "src"
    shutil.copytree(_EX, src)
    if rename:
        for suffix in (".meta", ".F90"):
            path = src / f"cld_ice{suffix}"
            path.write_text(re.sub(r"\bdyn_const_ice\b", "dyn_const", path.read_text()))
    tool = ccppMain()
    options_db = tool.default_options_db()
    out = tmp_path / "out"
    options_db.update({
        "suites": [str(src / "cld_suite.xml")],
        "scheme_files": [str(src / f"{s}.meta") for s in _SCHEMES],
        "host_files": [str(src / f"{h}.meta") for h in _HOSTS],
        "out": str(out),
        "tempdir": str(tmp_path / "tmp"),
        "verbose": 0,
    })
    tool.run(options_db)
    return "\n".join(p.read_text() for p in sorted(out.glob("*.F90")))


def test_shared_local_name_gets_one_array_per_standard_name(tmp_path):
    caps = _generate(tmp_path, rename=True)
    # cld_liq's and cld_ice's arrays are distinct cap variables, named from
    # their standard names, and both reach the constituent object.
    assert "lc_dynamic_constituents_for_cld_liq" in caps
    assert "lc_dynamic_constituents_for_cld_ice" in caps
    assert not re.search(r"\blc_dyn_const\b", caps)


def test_unique_local_names_keep_their_names(tmp_path):
    caps = _generate(tmp_path, rename=False)
    assert re.search(r"\blc_dyn_const\b", caps)
    assert re.search(r"\blc_dyn_const_ice\b", caps)
