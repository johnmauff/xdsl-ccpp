"""persistence is a capgen metadata property ('timestep', the default, or
'run': when a suite-owned array is allocated). xdsl_ccpp accepts and checks
it but does not act on it; CAM-SIMA's state_converters.meta declares
`persistence = timestep` on temp_to_potential_temp_run's theta."""

import pytest

from xdsl_ccpp.dialects.ccpp import ArgumentOp
from xdsl_ccpp.frontend.ccpp_xml import ccppXML, parse_meta_file
from xdsl_ccpp.util.errors import CcppInputError

_META = """\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
[ccpp-arg-table]
  name = scheme_a_run
  type = scheme
[ theta ]
  standard_name = air_potential_temperature
  units = K
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  intent = out
  persistence = {value}
"""


def _build(tmp_path, value):
    meta_file = tmp_path / "scheme_a.meta"
    meta_file.write_text(_META.format(value=value))
    frontend = ccppXML()
    return [frontend.build_meta_ir(m) for m in parse_meta_file(str(meta_file), True)]


def test_persistence_is_a_known_prop():
    assert "persistence" in ArgumentOp.KNOWN_PROPS


@pytest.mark.parametrize("value", ["timestep", "run", "Timestep"])
def test_accepted_without_a_warning(tmp_path, capsys, value):
    _build(tmp_path, value)
    assert "unrecognised" not in capsys.readouterr().err


def test_other_values_are_an_input_error(tmp_path):
    with pytest.raises(CcppInputError, match="persistence must be 'timestep' or 'run'"):
        _build(tmp_path, "forever")
