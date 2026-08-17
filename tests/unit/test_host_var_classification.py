"""Unit tests for cap_shared.classify_host_table_vars (Stage 1 of the
vocabulary-resolution redesign -- see ccpp_cap_refactor_plan.md).

Classification used by run_dispatch.py to distinguish host-owned "state" variables from fixed
CCPP-protocol dispatch scalars. It exists to tell apart, within xdsl_ccpp's own HOST-type
table, the small fixed set of CCPP-protocol dispatch scalars (loop bounds,
error handling -- legitimately threaded as plain arguments, matching real
capgen-v1's own lb/ub/errmsg/errflg convention) from genuine host-owned
state (real capgen-v1 resolves these via use-association; xdsl_ccpp
currently threads every HOST-type var as a block argument without
distinction, which is what the later redesign stages fix).

Fixture shape mirrors examples/opt_arg's own two host tables verbatim:
data.meta (all genuine state) and test_host.meta (all dispatch scalars).
"""

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.transforms.util.cap_shared import classify_host_table_vars
from xdsl_ccpp.transforms.util.ccpp_descriptors import BuildMetaDataDescriptions
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module

_STATE_SCHEME_META = f"""\
[ccpp-table-properties]
  name = state_scheme
  type = scheme
[ccpp-arg-table]
  name = state_scheme_run
  type = scheme
[ std_arg ]
  standard_name = std_arg
  units = 1
  type = integer
  dimensions = (size_of_std_arg)
  intent = in
{CCPP_MANDATORY_ARGS}
"""

# Verbatim shape of examples/opt_arg/data.meta -- genuine host-owned state.
_STATE_HOST_META = """\
[ccpp-table-properties]
  name = data
  type = host
  dependencies =
[ccpp-arg-table]
  name = data
  type = host
[nx]
  standard_name = size_of_std_arg
  units = count
  dimensions = ()
  type = integer
[std_arg]
  standard_name = std_arg
  units = 1
  dimensions = (size_of_std_arg)
  type = integer
[flag_for_opt_arg]
  standard_name = flag_for_opt_arg
  units = 1
  dimensions = ()
  type = logical
"""

# Verbatim shape of examples/opt_arg/test_host.meta -- pure dispatch scalars.
_DISPATCH_HOST_META = """\
[ccpp-table-properties]
  name = test_host
  type = host
[ccpp-arg-table]
  name = test_host
  type = host
[ col_start ]
  standard_name = horizontal_loop_begin
  type = integer
  units = count
  dimensions = ()
  protected = True
[ col_end ]
  standard_name = horizontal_loop_end
  type = integer
  units = count
  dimensions = ()
  protected = True
[ errmsg ]
  standard_name = ccpp_error_message
  units = none
  dimensions = ()
  type = character
  kind = len=512
[ errflg ]
  standard_name = ccpp_error_code
  units = 1
  dimensions = ()
  type = integer
"""


def _classify(run_host_match, ccpp_context) -> dict:
    module = run_host_match(
        scheme_metas=[_STATE_SCHEME_META],
        host_metas=[_STATE_HOST_META, _DISPATCH_HOST_META],
        suite_xml=minimal_suite_xml("state_scheme"),
    )
    ccpp_mod = find_ccpp_module(module.body.block.ops)
    bmdd = BuildMetaDataDescriptions()
    bmdd.traverse(ccpp_mod)
    return classify_host_table_vars(bmdd.meta_data)


def test_genuine_state_vars_classified_as_state(run_host_match, ccpp_context):
    classification = _classify(run_host_match, ccpp_context)
    assert classification["size_of_std_arg"] == "state"
    assert classification["std_arg"] == "state"
    assert classification["flag_for_opt_arg"] == "state"


def test_dispatch_scalars_classified_as_dispatch_scalar(run_host_match, ccpp_context):
    classification = _classify(run_host_match, ccpp_context)
    assert classification["horizontal_loop_begin"] == "dispatch_scalar"
    assert classification["horizontal_loop_end"] == "dispatch_scalar"
    assert classification["ccpp_error_message"] == "dispatch_scalar"
    assert classification["ccpp_error_code"] == "dispatch_scalar"


def test_classification_covers_every_host_var_exactly_once(run_host_match, ccpp_context):
    classification = _classify(run_host_match, ccpp_context)
    assert set(classification) == {
        "size_of_std_arg", "std_arg", "flag_for_opt_arg",
        "horizontal_loop_begin", "horizontal_loop_end",
        "ccpp_error_message", "ccpp_error_code",
    }
