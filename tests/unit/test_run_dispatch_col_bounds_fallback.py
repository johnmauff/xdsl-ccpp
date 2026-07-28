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
always present regardless of scheme content.

Must NOT double-insert col_start/col_end for suites where a scheme already
pulls them in via horizontal_loop_extent (helloworld, capgen, ddthost,
advection all rely on this) -- TestNoDuplicateWhenSchemeAlreadyProvidesThem
guards this.

Follow-up (found comparing xdsl-ccpp's generated Fortran against capgen-v1's
own): accepting col_start/col_end into the wrapper's own signature was
necessary but not sufficient. A second, separate bug meant they were never
actually threaded into the call to the suite callee: _build_run_block_
signature's fallback (above) only ever updated union_non_host_args, never
non_host_std_to_canonical -- the dict _build_run_dispatch_chain's
ArraySectionOp-slicing logic actually looks up. So a host array dimensioned
by horizontal_dimension (var_compat's real effrr/effrl/effrs/fluxLW/
sfc_up_sw/sfc_down_sw, and this test's own x_host) was passed to the suite
callee whole and unsliced on every call, regardless of col_start/col_end --
and a scheme scalar declaring standard_name=horizontal_dimension (var_compat's
own "ncol") was passed the host's raw, full column count instead of
col_end - col_start + 1. Under a driver that calls ccpp_physics_run in
column chunks (var_compat's test_host.F90 does; this was the confirmed root
cause of a real gfortran-verified effrs numerical mismatch), every chunk call
redundantly reprocessed the full array. Fixed by (a) also registering
non_host_std_to_canonical's CCPP_LOOP_BEGIN_STD_NAME/CCPP_LOOP_END_STD_NAME
entries in the same fallback block, (b) recomputing a horizontal_dimension-
standard_name scalar as col_end - col_start + 1 instead of passing the host's
raw value through, and (c) fixing a pre-existing, previously-unreachable bug
in the same ArraySectionOp block that required at least 2 resolved
dimensions (silently skipping any genuinely 1-D horizontal_dimension-only
array, e.g. var_compat's own fluxLW/sfc_up_sw/sfc_down_sw).
TestColBoundsSlicedWhenNoSchemeChunks (below, renamed from
TestColBoundsAcceptedWhenNoSchemeChunks) now asserts the corrected behavior.
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

_HOST_MOD_META_2D = """\
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
[ pver ]
  standard_name = vertical_layer_dimension
  units = count
  type = integer
  dimensions = ()
[ y_host ]
  standard_name = some_2d_array_var
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension,vertical_layer_dimension)
"""

_NCOL_SCHEME_META = f"""\
[ccpp-table-properties]
  name = ncol_scheme
  type = scheme
[ccpp-arg-table]
  name = ncol_scheme_run
  type = scheme
[ ncol ]
  standard_name = horizontal_dimension
  units = count
  type = integer
  dimensions = ()
  intent = in
[ y ]
  standard_name = some_2d_array_var
  units = m
  type = real
  kind = kind_phys
  dimensions = (horizontal_dimension,vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
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


def _fortran_output_ncol_scheme(run_host_match, ccpp_context) -> str:
    module = run_host_match(
        scheme_metas=[_NCOL_SCHEME_META],
        host_metas=[_HOST_META, _HOST_MOD_META_2D],
        suite_xml=minimal_suite_xml("ncol_scheme"),
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


class TestColBoundsSlicedWhenNoSchemeChunks:
    """whole_array_scheme is dimensioned by horizontal_dimension (the full
    array, matching var_compat's real schemes) -- no scheme here declares
    horizontal_loop_extent, so suite_cap.py never synthesizes a col_start/
    col_end parameter on the suite callee's own Fortran signature (that part
    is unchanged). But the wrapper-level col_start/col_end must still get
    threaded into the call as an ArraySectionOp slice on the host array
    (x_host), via non_host_std_to_canonical -- see module docstring."""

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

    def test_col_start_col_end_declared_integer_and_sliced_into_call(self, run_host_match, ccpp_context):
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
        # x_host is dimensioned by horizontal_dimension -- it must be sliced
        # by col_start:col_end at the call site, even though the suite
        # callee's own signature never declared col_start/col_end itself
        # (Fortran's assumed-shape dummy adapts to whatever section is
        # passed in). Passing the whole array here regardless of col_start/
        # col_end is exactly the bug that caused var_compat's real,
        # gfortran-verified effrs miscalculation under a chunked driver.
        assert "x_host(col_start:col_end)" in call_line, call_line


class TestHorizontalDimensionScalarRecomputedFromColBounds:
    """ncol_scheme declares a scalar arg (its own "ncol") with
    standard_name=horizontal_dimension -- matching var_compat's real
    effr_calc_run/rad_lw_run/rad_sw_run "ncol" args exactly. Passing the
    host's raw, full ncols through here (rather than recomputing
    col_end - col_start + 1) would tell the scheme its sliced array argument
    (y_host, below) is longer than it actually is -- confirmed to matter
    for var_compat's own rad_lw_run/rad_sw_run, whose `do icol = 1, ncol`
    loops would otherwise repeatedly write only the first chunk's columns
    and never reach the later chunks at all."""

    def test_ncol_recomputed_as_col_end_minus_col_start_plus_one(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output_ncol_scheme(run_host_match, ccpp_context)
        fn_body = fortran.split("subroutine Test_ccpp_physics_run")[1].split(
            "end subroutine Test_ccpp_physics_run"
        )[0]
        assert "col_end - col_start + 1" in fn_body, fn_body
        call_line = next(
            line for line in fn_body.splitlines() if "call test_suite_suite_physics" in line
        )
        assert "ncols" not in call_line, call_line

    def test_ncol_local_is_declared(self, run_host_match, ccpp_context):
        # A real gfortran build caught this: the recomputed value needs an
        # actual Fortran local-variable declaration (the alloca backing it is
        # necessarily nested inside the suite_name/suite_part dispatch chain's
        # scf.IfOps, not top-level in the wrapper's own block -- print_ftn.py's
        # local-alloca declaration collector used to only scan the top-level
        # block, so this declaration was silently dropped even though the
        # assignment/use were both printed correctly).
        # error: Symbol 'ncol' at (1) has no IMPLICIT type
        fortran = _fortran_output_ncol_scheme(run_host_match, ccpp_context)
        fn_body = fortran.split("subroutine Test_ccpp_physics_run")[1].split(
            "end subroutine Test_ccpp_physics_run"
        )[0]
        decl_lines = [line.strip() for line in fn_body.splitlines() if "integer :: ncol" in line]
        assert decl_lines, f"no 'integer :: ncol' declaration found:\n{fn_body}"

    def test_2d_horizontal_dimension_array_sliced_on_first_axis_only(
        self, run_host_match, ccpp_context
    ):
        # y_host is (horizontal_dimension, vertical_layer_dimension) --
        # matching effrr/effrl/effrs's real shape. Only the first axis is a
        # column-chunk bound; the second (pver) must stay the full 1:pver
        # range regardless of col_start/col_end.
        fortran = _fortran_output_ncol_scheme(run_host_match, ccpp_context)
        fn_body = fortran.split("subroutine Test_ccpp_physics_run")[1].split(
            "end subroutine Test_ccpp_physics_run"
        )[0]
        call_line = next(
            line for line in fn_body.splitlines() if "call test_suite_suite_physics" in line
        )
        assert "y_host(col_start:col_end, 1:pver)" in call_line, call_line


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
