"""Unit tests for run_dispatch.py's _build_run_block_signature col_start/
col_end fallback -- the host-facing ccpp_physics_run wrapper's own signature,
a separate layer from the suite subroutine's signature (suite_cap.py).

Found while investigating why examples/var_compat's generated
VarCompatibility_ccpp_physics_run only ever declared (suite_name, suite_part,
errmsg, errflg), while the hand-written test_host.F90 driver (which must not
be modified -- see feedback_dont_fix_handwritten_before_checking_upstream)
calls it with (suite_name, suite_part, col_start, col_end, errmsg, errflg).

Root cause: col_start/col_end only ever enter a suite callee's own signature
via suite_cap.py's _classify_args, which replaces a scheme-declared
horizontal_loop_extent arg with synthetic col_start/col_end scalars -- gated
entirely on some scheme in the suite declaring horizontal_loop_extent. When
every scheme in a suite is dimensioned by the full horizontal_dimension
instead (var_compat's actual, upstream-matching design -- none of its
schemes chunk by column), no suite callee ever gets a col_start/col_end
parameter, so run_dispatch.py's per-suite-arg classification
(_build_per_suite_run_info) has nothing to discover, and
union_non_host_args never picks them up either.

Every CCPP Fortran driver in this repo (helloworld, capgen, ddthost,
advection, var_compat) calls ccpp_physics_run with col_start/col_end
regardless of whether the suite is actually chunked -- and every host .meta
in this repo already declares col_start/col_end (standard_name
horizontal_loop_begin/horizontal_loop_end). Fixed by having
_build_run_block_signature accept them unconditionally whenever the host
declares them and no suite already supplied a col_start/col_end-equivalent
under some other local name (checked via seen_non_host_std_names, keyed by
standard_name so a differently-named host variable, e.g. "cols"/"cole",
still counts as already-supplied) -- mirroring how errmsg/errflg are already
always present regardless of scheme content. Unused inside the wrapper body
is fine: every Makefile in this repo already builds with
-Wno-unused-dummy-argument for exactly this class of argument.

Must NOT double-insert col_start/col_end for suites where a scheme already
pulls them in via horizontal_loop_extent (helloworld, capgen, ddthost,
advection all rely on this) -- TestNoDuplicateWhenSchemeAlreadyProvidesThem
guards this.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
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
[ col_start ]
  standard_name = horizontal_loop_begin
  units = count
  type = integer
  dimensions = ()
[ col_end ]
  standard_name = horizontal_loop_end
  units = count
  type = integer
  dimensions = ()
"""

_HOST_MOD_META = """\
[ccpp-table-properties]
  name = test_host_mod
  type = module
[ccpp-arg-table]
  name = test_host_mod
  type = module
[ ncols ]
  standard_name = horizontal_dimension
  units = count
  type = integer
  dimensions = ()
[ x_host ]
  standard_name = some_array_var
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
"""

_WHOLE_ARRAY_SCHEME_META = f"""\
[ccpp-table-properties]
  name = whole_array_scheme
  type = scheme
[ccpp-arg-table]
  name = whole_array_scheme_run
  type = scheme
[ x ]
  standard_name = some_array_var
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_CHUNKED_SCHEME_META = f"""\
[ccpp-table-properties]
  name = chunked_scheme
  type = scheme
[ccpp-arg-table]
  name = chunked_scheme_run
  type = scheme
[ ncol ]
  standard_name = horizontal_loop_extent
  units = count
  type = integer
  dimensions = ()
  intent = in
[ x ]
  standard_name = some_array_var
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_loop_extent)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""


def _fortran_output(run_host_match, ccpp_context, scheme_meta) -> str:
    module = run_host_match(
        scheme_metas=[scheme_meta],
        host_metas=[_HOST_META, _HOST_MOD_META],
        suite_xml=minimal_suite_xml("whole_array_scheme" if "whole_array" in scheme_meta else "chunked_scheme"),
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fn_signature_line(fortran: str, fn_name: str) -> str:
    """Return the (possibly line-wrapped) subroutine header, joined into one
    line, up to the first declaration statement."""
    body = fortran.split(f"subroutine {fn_name}")[1]
    header_lines = []
    for line in body.splitlines()[0:6]:
        header_lines.append(line.strip().rstrip("&").strip())
        if line.rstrip().endswith(")") and "&" not in line:
            break
    return " ".join(header_lines)


class TestColBoundsAcceptedWhenNoSchemeChunks:
    """whole_array_scheme is dimensioned by horizontal_dimension (the full
    array, matching var_compat's real schemes) -- no scheme here declares
    horizontal_loop_extent, so suite_cap.py never synthesizes a col_start/
    col_end parameter on the suite callee at all."""

    def test_wrapper_signature_includes_col_start_col_end(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context, _WHOLE_ARRAY_SCHEME_META)
        sig = _fn_signature_line(fortran, "Test_ccpp_physics_run")
        assert "col_start" in sig, f"col_start missing from wrapper signature: {sig!r}"
        assert "col_end" in sig, f"col_end missing from wrapper signature: {sig!r}"
        # Position: right after suite_name/suite_part, before errmsg/errflg --
        # matches every hand-written driver's calling convention exactly.
        names = [n.strip() for n in sig.split("(", 1)[1].rsplit(")", 1)[0].split(",")]
        assert names[:4] == ["suite_name", "suite_part", "col_start", "col_end"], (
            f"unexpected argument order: {names!r}"
        )
        assert names[-2:] == ["errmsg", "errflg"]

    def test_col_start_col_end_declared_integer_and_unused_in_call(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context, _WHOLE_ARRAY_SCHEME_META)
        fn_body = fortran.split("subroutine Test_ccpp_physics_run")[1].split(
            "end subroutine Test_ccpp_physics_run"
        )[0]
        col_start_decl = next(
            line for line in fn_body.splitlines() if "intent(in) :: col_start" in line
        )
        assert "integer" in col_start_decl
        call_line = next(
            line for line in fn_body.splitlines() if "call test_suite_suite_physics" in line
        )
        # The suite callee never declared col_start/col_end (no scheme here
        # pulls them in), so they must not appear in the call at all --
        # confirms they're a genuine, honest pass-through accept-and-ignore,
        # not silently (and wrongly) threaded into the callee.
        assert "col_start" not in call_line
        assert "col_end" not in call_line


class TestNoDuplicateWhenSchemeAlreadyProvidesThem:
    """chunked_scheme declares horizontal_loop_extent directly -- col_start/
    col_end already flow through the pre-existing, proven mechanism
    (suite_cap.py's _classify_args). The new host-driven fallback must
    detect this (via seen_non_host_std_names) and add nothing extra --
    otherwise every already-working chunked example (helloworld, capgen,
    ddthost, advection) would regress with a duplicate dummy argument."""

    def test_col_start_col_end_appear_exactly_once(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context, _CHUNKED_SCHEME_META)
        sig = _fn_signature_line(fortran, "Test_ccpp_physics_run")
        names = [n.strip() for n in sig.split("(", 1)[1].rsplit(")", 1)[0].split(",")]
        assert names.count("col_start") == 1, f"col_start duplicated: {names!r}"
        assert names.count("col_end") == 1, f"col_end duplicated: {names!r}"

    def test_col_start_col_end_threaded_into_the_call(self, run_host_match, ccpp_context):
        """Sanity check that this suite's own col_start/col_end really are
        the pre-existing, scheme-driven kind (threaded into the callee),
        distinguishing this case from the pure pass-through case above."""
        fortran = _fortran_output(run_host_match, ccpp_context, _CHUNKED_SCHEME_META)
        fn_body = fortran.split("subroutine Test_ccpp_physics_run")[1].split(
            "end subroutine Test_ccpp_physics_run"
        )[0]
        call_line = next(
            line for line in fn_body.splitlines() if "call test_suite_suite_physics" in line
        )
        assert "col_start" in call_line
        assert "col_end" in call_line
