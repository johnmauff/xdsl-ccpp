"""The GPU data pass finds a scheme argument's suite block argument by its
standard name (the suite cap records them as arg_attrs), not by trying
scheme local names.

scheme_a and scheme_b both name an argument x, for different host
variables, so the suite cap names those dummy arguments host_a and host_b.
host_a is device-resident and its schemes disagree (scheme_a uses it on the
device, scheme_c on the host), so each call gets present/update routing.
Looking the block argument up by the schemes' local names (x, y) found
neither, and no routing was emitted.
"""

import os
import re

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.tools.ccpp_dsl import ccppMain


def _scheme(name, local, std, device):
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
[ {local} ]
  standard_name = {std}
  units = 1
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension)
  intent = inout
{"  memory_space = device" + chr(10) if device else ""}{CCPP_MANDATORY_ARGS}"""


_HOST = """\
[ccpp-table-properties]
  name = gd_host_mod
  type = module
[ccpp-arg-table]
  name = gd_host_mod
  type = module
[ ncols ]
  standard_name = horizontal_dimension
  units = count
  type = integer
  dimensions = ()
[ host_a ]
  standard_name = quantity_a
  units = 1
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension)
  memory_space = device
[ host_b ]
  standard_name = quantity_b
  units = 1
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension)
"""


def test_diverged_var_found_by_standard_name(tmp_path):
    schemes = [("scheme_a", "x", "quantity_a", True),
               ("scheme_b", "x", "quantity_b", False),
               ("scheme_c", "y", "quantity_a", False)]
    for name, local, std, device in schemes:
        (tmp_path / f"{name}.meta").write_text(_scheme(name, local, std, device))
    (tmp_path / "gd_host_mod.meta").write_text(_HOST)
    (tmp_path / "s.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<suite name="s" version="2.0">\n  <group name="g">\n'
        + "".join(f"    <scheme>{n}</scheme>\n" for n, *_ in schemes)
        + "  </group>\n</suite>\n")
    tool = ccppMain()
    options_db = tool.default_options_db()
    options_db.update({
        "suites": [str(tmp_path / "s.xml")],
        "scheme_files": [str(tmp_path / f"{n}.meta") for n, *_ in schemes],
        "host_files": [str(tmp_path / "gd_host_mod.meta")],
        "host_name": "gd_host",
        "out": str(tmp_path / "out"),
        "tempdir": str(tmp_path / "tmp"),
        "verbose": 0,
        "directive": "acc",
    })
    result = tool.run(options_db)
    suite = next(open(os.path.join(options_db["out"], p)).read()
                 for p in result.written if p.endswith("s_cap.F90"))
    assert re.search(r"subroutine s_g\([^)]*\bhost_a\b", re.sub(r"&\s*\n\s*", "", suite))
    # scheme_a uses host_a on the device: present; scheme_c on the host: update.
    assert re.search(r"!\$acc data present\(host_a\)", suite), suite
    assert re.search(r"!\$acc update self\(host_a\)", suite)
    assert re.search(r"!\$acc update device\(host_a\)", suite)
