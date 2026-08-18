"""Regression test for a real gfortran CI compile failure found while wiring
examples/instances into the real build (ccpp_cap_refactor_plan.md's
"instances/instances_advection" backlog entry, Stage 5):

    Error: Symbol 'flag_for_opt_array' at (1) has no IMPLICIT type

Root cause: suite_cap.py's `active = <expr>` property resolution
(_resolve_active_condition) only ever resolved a MODULE-type or
'state'-classified HOST-type standard-name reference to its real local
Fortran name. A reference to a DDT member (examples/instances' own
flag_for_opt_array, a member of the instance_type DDT) fell through to the
"unresolved token, assume it's a Fortran keyword/operator" default and got
printed VERBATIM as the bare standard-name text -- which is not a real
Fortran identifier anywhere in the generated module.

This never surfaced before because the only other example exercising this
mechanism (examples/opt_arg's own flag_for_opt_arg) happens to have a local
variable name identical to its standard name, so printing the raw
standard-name text verbatim happened to compile by coincidence, not because
the resolution was actually correct.

Fixed by adding DDT-member resolution to _resolve_active_condition, reusing
the same _resolve_ddt_access_path machinery run_dispatch.py's own DDT-member
resolution already uses -- including the array-of-DDT-instance case (real
capgen-v1's multi-instance model, same backlog entry): when the DDT's own
module-level instance is itself a HOST-owned array of model instances, the
resolved reference is indexed by the calling scheme's own sibling
instance_number-standard-name arg (e.g. `instance_data(instance)%
opt_array_flag`), not just `instance_data%opt_array_flag`.
"""

from io import StringIO

import pytest

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

_HOST_META = """\
[ccpp-table-properties]
  name = data
  type = host
[ccpp-arg-table]
  name = data
  type = host
[ instance ]
  standard_name = instance_number
  units = index
  type = integer
  dimensions = ()
[ instance_data ]
  standard_name = instance_data
  units = ddt
  type = instance_type
  dimensions = (number_of_instances)
"""

_DDT_META = """\
[ccpp-table-properties]
  name = instance_type
  type = ddt
[ccpp-arg-table]
  name = instance_type
  type = ddt
[ opt_array_flag ]
  standard_name = flag_for_opt_array
  units = flag
  type = logical
  dimensions = ()
[ arr_member ]
  standard_name = data_array_opt_std
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  active = (flag_for_opt_array)
"""

_SCHEME_META = f"""\
[ccpp-table-properties]
  name = unit_conv_scheme
  type = scheme
[ccpp-arg-table]
  name = unit_conv_scheme_run
  type = scheme
[ instance ]
  standard_name = instance_number
  units = index
  type = integer
  dimensions = ()
  intent = in
[ arr ]
  standard_name = data_array_opt_std
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  intent = inout
  optional = True
{CCPP_MANDATORY_ARGS}
"""


def _fortran_output(run_host_match, ccpp_context) -> str:
    module = run_host_match(
        scheme_metas=[_SCHEME_META],
        host_metas=[_HOST_META, _DDT_META],
        suite_xml=minimal_suite_xml("unit_conv_scheme"),
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


class TestActiveConditionResolvesArrayOfInstanceDdtMember:
    def test_condition_is_indexed_member_reference_not_bare_standard_name(
        self, run_host_match, ccpp_context
    ):
        """The printed condition must be a real Fortran reference
        (instance_data(instance)%opt_array_flag), not the bare
        standard-name text (flag_for_opt_array) that has no IMPLICIT type
        anywhere in the generated module."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        assert "instance_data(instance)%opt_array_flag" in fortran
        assert "flag_for_opt_array" not in fortran

    def test_use_stub_emitted_for_the_bare_array_name(self, run_host_match, ccpp_context):
        """The USE statement must be for the bare array name (instance_data),
        never for the standard-name text or the indexed expression."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        assert "use data, only: instance_data" in fortran


class TestActiveConditionRaisesWithoutSiblingInstanceArg:
    def test_missing_instance_number_sibling_raises(self, run_host_match, ccpp_context):
        """Without a sibling instance_number arg in the same call, there's no
        way to know which instance to test -- must raise clearly, not
        silently emit an unindexed (and therefore wrong) reference."""
        scheme_meta_no_instance = f"""\
[ccpp-table-properties]
  name = unit_conv_scheme
  type = scheme
[ccpp-arg-table]
  name = unit_conv_scheme_run
  type = scheme
[ arr ]
  standard_name = data_array_opt_std
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  intent = inout
  optional = True
{CCPP_MANDATORY_ARGS}
"""
        with pytest.raises(ValueError, match="instance_number"):
            module = run_host_match(
                scheme_metas=[scheme_meta_no_instance],
                host_metas=[_HOST_META, _DDT_META],
                suite_xml=minimal_suite_xml("unit_conv_scheme"),
            )
            ArgOwnershipPass().apply(ccpp_context, module)
            SuiteCAP().apply(ccpp_context, module)
