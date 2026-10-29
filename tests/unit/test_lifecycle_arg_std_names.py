"""The host cap's lifecycle wrappers built by lifecycle_cap.py
(ccpp_register, ccpp_init, ccpp_final; the group phases go through
run_dispatch.py) resolve the suite callee's arguments by the standard names
the suite cap records on it (suite_arg_attrs), not by scheme local names.

Two schemes' _register entry points use the same local name, x, for
different host variables. The suite cap names those dummy arguments after
the host variables (host_a, host_b); resolving them by scheme local name
found neither, and ccpp_register passed uninitialized locals instead.
"""

import os
import re

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.tools.ccpp_dsl import ccppMain

_SCHEME = """\
[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_register
  type = scheme
[ x ]
  standard_name = {std}
  units = 1
  type = real | kind = kind_phys
  dimensions = ()
  intent = in
{mandatory}[ccpp-arg-table]
  name = {name}_run
  type = scheme
{mandatory}"""

_HOST = """\
[ccpp-table-properties]
  name = lc_host_mod
  type = module
[ccpp-arg-table]
  name = lc_host_mod
  type = module
[ host_a ]
  standard_name = quantity_a
  units = 1
  type = real | kind = kind_phys
  dimensions = ()
[ host_b ]
  standard_name = quantity_b
  units = 1
  type = real | kind = kind_phys
  dimensions = ()
"""


def test_register_wrapper_passes_host_vars_for_colliding_local_names(tmp_path):
    for name, std in (("scheme_a", "quantity_a"), ("scheme_b", "quantity_b")):
        (tmp_path / f"{name}.meta").write_text(
            _SCHEME.format(name=name, std=std, mandatory=CCPP_MANDATORY_ARGS))
    (tmp_path / "lc_host_mod.meta").write_text(_HOST)
    (tmp_path / "s.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<suite name="s" version="2.0">\n'
        '  <group name="g">\n    <scheme>scheme_a</scheme>\n    <scheme>scheme_b</scheme>\n'
        '  </group>\n</suite>\n')
    tool = ccppMain()
    options_db = tool.default_options_db()
    options_db.update({
        "suites": [str(tmp_path / "s.xml")],
        "scheme_files": [str(tmp_path / "scheme_a.meta"), str(tmp_path / "scheme_b.meta")],
        "host_files": [str(tmp_path / "lc_host_mod.meta")],
        "host_name": "lc_host",
        "out": str(tmp_path / "out"),
        "tempdir": str(tmp_path / "tmp"),
        "verbose": 0,
    })
    result = tool.run(options_db)
    host = next(open(os.path.join(options_db["out"], p)).read()
                for p in result.written if p.endswith("_ccpp_cap.F90"))
    host = re.sub(r"&\s*\n\s*", "", host)
    call = re.search(r"call s_register\((.*)\)", host).group(1)
    assert "host_a" in call and "host_b" in call, call
    assert "lc_host_a" not in call and "lc_host_b" not in call, call
    assert re.search(r"use lc_host_mod, only: .*host_a", host)
