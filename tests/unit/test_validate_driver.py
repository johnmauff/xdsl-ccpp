"""Unit tests for ccpp_validate_driver -- checking a host-driver program's
own errmsg/errflg locals against the CCPP protocol's fixed convention
(character(len=512) / integer), reusing compare_arg_tables/Mismatch.

ccpp-validator-length-check (BACKLOG.md): examples/instances/main.F90's
character(len=256) :: errmsg is a real, deliberately-preserved mismatch
against the generated cap's character(len=512) dummy argument -- verbatim
capgen-v1 upstream content, exercising a known gap in capgen-v1's own
validator. This test suite is the regression guard proving the new check
actually catches it (and doesn't false-positive on lookalikes).
"""

from pathlib import Path

import pytest

pytest.importorskip("fparser", reason="fparser not installed")

from xdsl_ccpp.tools.ccpp_validate_driver import check_driver_file

# The one documented, intentional exception: examples/instances/main.F90's
# errmsg is deliberately preserved verbatim capgen-v1 upstream content (a
# known, real gap in capgen-v1's own validator -- see BACKLOG.md's
# ccpp-validator-length-check / CHANGELOG.md's resolution entry). Any OTHER
# example file flagged here is a real, new regression, not an expected one.
_KNOWN_EXCEPTIONS = {"examples/instances/main.F90"}


class TestRealDetection:
    def test_instances_main_flags_length_mismatch(self):
        mismatches = check_driver_file("examples/instances/main.F90")
        assert len(mismatches) == 1
        m = mismatches[0]
        assert m.arg_name == "errmsg"
        assert m.field == "kind"
        # Normalise whitespace before comparing -- fparser2's own
        # str()-serialization inserts spaces around '=' (e.g. "len = 256"),
        # independent of how the real source spells it ("len=256", no
        # spaces); compare_arg_tables itself normalises the same way when
        # deciding whether something mismatches at all.
        assert m.meta_value.replace(" ", "") == "len=512"
        assert m.fir_value.replace(" ", "") == "len=256"


class TestCleanPass:
    def test_threads_main_matches_convention(self):
        assert check_driver_file("examples/threads/main.F90") == []

    def test_constituents_dim_main_matches_convention(self):
        assert check_driver_file("examples/constituents_dim/main.F90") == []


class TestNoFalsePositiveOnModuleScopedLookalike:
    def test_capgen_test_utils_module_local_not_flagged(self):
        # examples/capgen/host_ftn/test_utils.F90 declares its own unrelated
        # character(len=256) :: errmsg as a local scratch variable inside a
        # module-level function (check_list), never passed to any generated
        # cap call. This file has no `program ... end program` block at all,
        # so extract_program_locals must find nothing to extract here --
        # proving the Main_Program-only scoping decision is correct, not
        # just assumed.
        assert check_driver_file("examples/capgen/host_ftn/test_utils.F90") == []

    def test_ddthost_test_utils_module_local_not_flagged(self):
        assert check_driver_file("examples/ddthost/host_ftn/test_utils.F90") == []


class TestOmittedCharacterLengthNotSilentlyAccepted:
    """Copilot PR #135 finding: a bare `character :: errmsg` (no length
    selector at all -- Fortran's own default is len=1) must not slip past
    as a match. compare_arg_tables only compares kind when BOTH sides
    supply one, so _actual_table must give an omitted length an explicit,
    comparable value instead of leaving it unset.
    """

    def test_bare_character_errmsg_flagged(self, tmp_path):
        f90 = tmp_path / "bad_errmsg_len.F90"
        f90.write_text(
            "program bad_errmsg_len\n"
            "  character :: errmsg\n"
            "  integer :: errflg\n"
            "  errflg = 0\n"
            "end program bad_errmsg_len\n"
        )
        mismatches = check_driver_file(str(f90))
        assert len(mismatches) == 1
        m = mismatches[0]
        assert m.arg_name == "errmsg"
        assert m.field == "kind"
        assert m.meta_value.replace(" ", "") == "len=512"
        assert m.fir_value.replace(" ", "") == "len=1"


class TestNonScalarShapeMisclassifiedAsScalar:
    """Copilot PR #135 finding: rank counting only recognised
    Assumed_Shape_Spec/Explicit_Shape_Spec, so a deferred-shape
    `errmsg(:)` computed rank 0 -- identical to a real scalar -- and
    silently passed the required scalar comparison.
    """

    def test_deferred_shape_errmsg_flagged(self, tmp_path):
        f90 = tmp_path / "bad_errmsg_shape.F90"
        f90.write_text(
            "program bad_errmsg_shape\n"
            "  character(len=512), allocatable :: errmsg(:)\n"
            "  integer :: errflg\n"
            "  errflg = 0\n"
            "end program bad_errmsg_shape\n"
        )
        mismatches = check_driver_file(str(f90))
        assert len(mismatches) == 1
        m = mismatches[0]
        assert m.arg_name == "errmsg"
        assert m.field == "rank"
        assert m.meta_value == "0"
        assert m.fir_value == "1"


class TestAllExamplesSweep:
    """CI wiring: sweeps every real .F90 file under examples/, not just the
    handful picked above -- so a brand-new example's driver repeating this
    same mistake gets caught automatically, without needing its own test.
    Runs in the existing pytest CI job (tests.yml); no new CI workflow/job
    needed, and no blanket compile-matrix carve-out required either, since
    this check needs no compiler at all.
    """

    def test_only_the_known_exception_is_flagged(self):
        all_f90 = sorted(
            str(p) for p in Path("examples").rglob("*.F90")
        )
        assert all_f90, "expected to find example .F90 files -- sweep found none"

        flagged = {}
        for path in all_f90:
            mismatches = check_driver_file(path)
            if mismatches:
                flagged[path] = mismatches

        unexpected = {p: m for p, m in flagged.items() if p not in _KNOWN_EXCEPTIONS}
        assert not unexpected, (
            "New, unexpected driver-convention mismatch(es) found:\n"
            + "\n".join(f"{p}:\n" + "\n".join(str(m) for m in ms) for p, ms in unexpected.items())
        )

        # The known exception must still actually BE the known issue -- if
        # it ever stops being flagged, that's this backlog item's fix
        # landing in examples/instances/main.F90 itself (not expected per
        # the backlog note, but if it happens, this assertion should be
        # relaxed/removed, not silently left stale).
        assert set(flagged) == _KNOWN_EXCEPTIONS
