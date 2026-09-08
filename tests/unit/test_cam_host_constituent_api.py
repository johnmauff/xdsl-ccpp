"""Regression tests for the CAM-host branch of _generate_constituent_api.

Copilot PR #97 comment (line 850): the unified implementation has no automated
coverage for cam_host=True.  All existing FileCheck fixtures exercise
NonCamHostConstituentApiOp; no test invokes CCPPCAP(cam_host=True).

Tests here cover the three CAM-specific invariants called out in that comment:
  1. CAM positional signature in register_constituents: (host_constituents,
     errcode, errmsg) -- NOT the non-CAM order (errmsg, errcode).
  2. register body calls ccpp_initialize_constituent_ptr (not
     ccpp_scheme_utils_set_constituents).
  3. gather_constituents and update_constituents subroutines are emitted and
     contain copy_in / copy_out calls on cam_constituents_obj.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

_HOST_META = """\
[ccpp-table-properties]
  name = test_host
  type = host
[ccpp-arg-table]
  name = test_host
  type = host
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

# The run entry intentionally uses only the mandatory args so the CAM lifecycle
# wrapper (_generate_cam_lifecycle_wrappers) does not need host variables beyond
# what _CAM_STD_EXPRS provides.  The tests here are about the constituent API
# module-level subroutines (register/gather/update), not the run dispatcher.
_SCHEME_META = f"""\
[ccpp-table-properties]
  name = cld_liq
  type = scheme
[ccpp-arg-table]
  name = cld_liq_register
  type = scheme
[ dyn_const ]
  standard_name = dynamic_constituents_for_cld_liq
  dimensions = (:)
  type = ccpp_constituent_properties_t
  intent = out
  allocatable = true
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = cld_liq_run
  type = scheme
{CCPP_MANDATORY_ARGS}
"""

_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <scheme>cld_liq</scheme>
  </group>
</suite>
"""


def _fortran_output(run_host_match, ccpp_context) -> str:
    module = run_host_match(
        scheme_metas=[_SCHEME_META],
        host_metas=[_HOST_META],
        suite_xml=_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP(cam_host=True).apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fn_body(fortran: str, fn_name: str) -> str:
    return fortran.split(f"subroutine {fn_name}")[1].split(f"end subroutine {fn_name}")[0]


def _unwrapped(fortran_fragment: str) -> str:
    """Collapse Fortran line-continuation ('&' + newline + indent) into one string."""
    return " ".join(
        line.rstrip().rstrip("&").strip() for line in fortran_fragment.splitlines()
    )


# The suite name "test_suite" strips the "_suite" suffix and CamelCases to "Test",
# so all constituent API subroutines use the "Test_" prefix.
_REGISTER_FN = "Test_ccpp_register_constituents"
_GATHER_FN   = "Test_ccpp_gather_constituents"
_UPDATE_FN   = "Test_ccpp_update_constituents"


class TestCamHostRegisterConstituentsSignature:
    def test_cam_positional_arg_order(self, run_host_match, ccpp_context):
        """register_constituents must declare (host_constituents, errcode, errmsg)
        in that order -- the CAM calling convention.  The non-CAM order is
        (host_constituents, errmsg, errcode); regressing this means integer and
        character arguments swap positions at every CAM call site."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        body = _fn_body(fortran, _REGISTER_FN)
        sig = _unwrapped(body.split("implicit none")[0])
        errcode_pos = sig.index("errcode")
        errmsg_pos = sig.index("errmsg")
        assert errcode_pos < errmsg_pos, (
            f"CAM register_constituents: errcode must precede errmsg in arg list; "
            f"got: {sig!r}"
        )

    def test_cam_uses_initialize_constituent_ptr(self, run_host_match, ccpp_context):
        """register_constituents body must call ccpp_initialize_constituent_ptr
        (the CAM object API), not ccpp_scheme_utils_set_constituents
        (the non-CAM path)."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        body = _fn_body(fortran, _REGISTER_FN)
        assert "ccpp_initialize_constituent_ptr" in body
        assert "ccpp_scheme_utils_set_constituents" not in body


class TestCamHostGatherUpdateRoutines:
    def test_gather_constituents_is_emitted(self, run_host_match, ccpp_context):
        """gather_constituents subroutine must be present in CAM-host output."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        assert f"subroutine {_GATHER_FN}" in fortran

    def test_gather_constituents_calls_copy_in(self, run_host_match, ccpp_context):
        """gather_constituents body must call cam_constituents_obj%copy_in."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        body = _fn_body(fortran, _GATHER_FN)
        assert "cam_constituents_obj%copy_in" in body

    def test_update_constituents_is_emitted(self, run_host_match, ccpp_context):
        """update_constituents subroutine must be present in CAM-host output."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        assert f"subroutine {_UPDATE_FN}" in fortran

    def test_update_constituents_calls_copy_out(self, run_host_match, ccpp_context):
        """update_constituents body must call cam_constituents_obj%copy_out."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        body = _fn_body(fortran, _UPDATE_FN)
        assert "cam_constituents_obj%copy_out" in body

    def test_gather_update_in_public_names(self, run_host_match, ccpp_context):
        """Both gather and update routine names must appear in explicit
        ``public ::`` declarations so the stated invariant fails if they are
        dropped from public_names_list (not just present in the subroutine
        definition lines, which would also contain the names)."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        assert f"public :: {_GATHER_FN}" in fortran
        assert f"public :: {_UPDATE_FN}" in fortran
