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

import pytest

pytest.importorskip("fparser", reason="fparser not installed")

from xdsl_ccpp.tools.ccpp_validate_driver import check_driver_file


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
