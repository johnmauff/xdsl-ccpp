"""Regression tests for recognizing top_at_one as a real metadata attribute.

Stage 1 of the vertical-flip work (examples/var_compat's effr_calc/effr_diag
declare top_at_one = True on some arguments). Before this, top_at_one was
silently dropped with an "unrecognised keys" warning (ArgumentOp.KNOWN_PROPS
in xdsl_ccpp/dialects/ccpp.py, checked in ccpp_xml.py). This stage only adds
recognition -- nothing acts on the attribute yet; that's a later stage.
"""

from xdsl_ccpp.dialects.ccpp import ArgumentOp
from xdsl_ccpp.frontend.ccpp_xml import parse_meta_file
from xdsl_ccpp.transforms.suite_meta import MetaCAP

_SCHEME_META = """\
[ccpp-table-properties]
  name = scheme_a
  type = scheme
[ccpp-arg-table]
  name = scheme_a_run
  type = scheme
[ x ]
  standard_name = shared_var
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  intent = inout
  top_at_one = True
[ errmsg ]
  standard_name = ccpp_error_message
  long_name = Error message for error handling in CCPP
  type = character
  kind = len=512
  intent = out
  dimensions = ()
  units = none
[ errflg ]
  standard_name = ccpp_error_code
  long_name = Error flag for error handling in CCPP
  type = integer
  intent = out
  dimensions = ()
  units = 1
"""


def test_top_at_one_is_a_known_prop():
    assert "top_at_one" in ArgumentOp.KNOWN_PROPS


def test_no_unrecognised_key_warning(tmp_path, capsys):
    meta_file = tmp_path / "scheme_a.meta"
    meta_file.write_text(_SCHEME_META)
    list(parse_meta_file(str(meta_file), True))
    captured = capsys.readouterr()
    assert "top_at_one" not in captured.err
    assert "top_at_one" not in captured.out


def test_arg_op_carries_top_at_one(tmp_path, ccpp_context, build_module):
    module = build_module([_SCHEME_META], [])
    MetaCAP().apply(ccpp_context, module)

    found = []

    def _walk(op):
        if isinstance(op, ArgumentOp) and op.arg_name.data == "x":
            found.append(op)
        for region in op.regions:
            for block in region.blocks:
                for inner in block.ops:
                    _walk(inner)

    for op in module.ops:
        _walk(op)

    assert found, "expected to find the 'x' ArgumentOp"
    assert found[0].top_at_one is not None
